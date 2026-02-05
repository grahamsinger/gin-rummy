"""Monte Carlo simulation-based AI opponent for Gin Rummy."""

from __future__ import annotations

import logging
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from gin_rummy.models import Card, Hand, Suit, Rank, analyze_hand
from gin_rummy.models.melds import calculate_layoff
from gin_rummy.config import get_config, Config
from gin_rummy.ai.types import (
    DrawChoice,
    DrawReasoning,
    DiscardReasoning,
    KnockReasoning,
)
from gin_rummy.ai.context_aware import ContextAwareAI
from gin_rummy.ai.basic import BasicAI

if TYPE_CHECKING:
    from gin_rummy.context import GameContext


logger = logging.getLogger(__name__)

# Full deck for set operations
ALL_CARDS = frozenset(Card(rank, suit) for rank in Rank for suit in Suit)


@dataclass
class RolloutResult:
    """Result of a single rollout simulation."""

    my_points: int  # Points scored (positive = good for me)
    is_draw: bool  # Round ended in draw (deck exhausted)
    i_knocked: bool  # Whether I was the knocker
    terminated_early: bool  # Hit max_turns limit


def score_knock(
    knocker_hand: list[Card],
    defender_hand: list[Card],
    gin_bonus: int = 25,
    undercut_bonus: int = 25,
    knock_threshold: int = 10,
) -> tuple[int, bool, bool]:
    """Score a knock from the knocker's perspective.

    Returns:
        Tuple of (points_for_knocker, is_gin, is_undercut).
        points_for_knocker is negative if undercut.
    """
    knocker_analysis = analyze_hand(knocker_hand)
    knocker_deadwood = knocker_analysis.deadwood_value

    if knocker_deadwood > knock_threshold:
        # Can't knock -- shouldn't happen but handle gracefully
        return 0, False, False

    is_gin = knocker_deadwood == 0

    if is_gin:
        defender_analysis = analyze_hand(defender_hand)
        defender_deadwood = defender_analysis.deadwood_value
        return gin_bonus + defender_deadwood, True, False
    else:
        # Defender can lay off
        layoff_result = calculate_layoff(defender_hand, knocker_analysis.melds)
        defender_deadwood = layoff_result.deadwood_after

        is_undercut = defender_deadwood <= knocker_deadwood
        if is_undercut:
            points = -(undercut_bonus + (knocker_deadwood - defender_deadwood))
            return points, False, True
        else:
            points = defender_deadwood - knocker_deadwood
            return points, False, False


def evaluate_terminal(
    my_hand: list[Card],
    opp_hand: list[Card],
    knock_threshold: int = 10,
) -> int:
    """Evaluate a terminal position heuristically when rollout hits max_turns.

    Combines deadwood difference with meld structure and knock proximity
    for a richer signal than raw deadwood diff alone.

    Returns:
        Score from my perspective (positive = good for me).
    """
    my_analysis = analyze_hand(my_hand)
    opp_analysis = analyze_hand(opp_hand)

    my_deadwood = my_analysis.deadwood_value
    opp_deadwood = opp_analysis.deadwood_value

    # Primary: deadwood difference
    score = opp_deadwood - my_deadwood

    # Meld count bonus: having more melds is structurally better
    meld_diff = len(my_analysis.melds) - len(opp_analysis.melds)
    score += meld_diff * 2

    # Knock proximity: bonus for being close to knock threshold, penalty if far
    if my_deadwood <= knock_threshold:
        score += (knock_threshold - my_deadwood) // 2
    if opp_deadwood <= knock_threshold:
        score -= (knock_threshold - opp_deadwood) // 2

    return score


def rollout(
    my_hand: list[Card],
    opp_hand: list[Card],
    deck: list[Card],
    discard_pile: list[Card],
    my_turn: bool,
    rollout_ai: BasicAI,
    max_turns: int = 8,
    knock_threshold: int = 10,
    gin_bonus: int = 25,
    undercut_bonus: int = 25,
) -> RolloutResult:
    """Simulate a game from an arbitrary state without using the Game class.

    Both sides use the rollout_ai for decisions. Alternates turns until
    someone knocks, gin is achieved, deck exhausted, or max_turns hit.

    Args:
        my_hand: Cards in my hand (will be mutated).
        opp_hand: Cards in opponent's hand (will be mutated).
        deck: Remaining deck cards (will be mutated, draw from end).
        discard_pile: Current discard pile (will be mutated).
        my_turn: Whether it's my turn to act first.
        rollout_ai: AI instance to use for decisions.
        max_turns: Maximum turns before heuristic evaluation.
        knock_threshold: Deadwood threshold for knocking.
        gin_bonus: Bonus for gin.
        undercut_bonus: Bonus for undercut.

    Returns:
        RolloutResult with outcome from my perspective.
    """
    turns_played = 0

    while turns_played < max_turns:
        if len(deck) <= 2:
            return RolloutResult(my_points=0, is_draw=True, i_knocked=False, terminated_early=False)

        current_hand = my_hand if my_turn else opp_hand

        # Draw decision
        discard_top = discard_pile[-1] if discard_pile else None
        hand_obj = Hand(current_hand)
        draw_choice = rollout_ai.decide_draw(hand_obj, discard_top)

        # Execute draw
        if draw_choice == DrawChoice.DISCARD and discard_pile:
            drawn = discard_pile.pop()
        else:
            drawn = deck.pop()
        current_hand.append(drawn)

        # Discard decision
        hand_obj = Hand(current_hand)
        discard_card = rollout_ai.decide_discard(hand_obj)
        current_hand.remove(discard_card)
        discard_pile.append(discard_card)

        # Knock check
        hand_obj = Hand(current_hand)
        deadwood = hand_obj.deadwood_total

        if deadwood <= knock_threshold:
            should_knock = rollout_ai.should_knock(hand_obj)
            if should_knock:
                # Score the knock
                if my_turn:
                    points, is_gin, is_undercut = score_knock(
                        current_hand,
                        opp_hand,
                        gin_bonus,
                        undercut_bonus,
                        knock_threshold,
                    )
                    return RolloutResult(
                        my_points=points,
                        is_draw=False,
                        i_knocked=True,
                        terminated_early=False,
                    )
                else:
                    points, is_gin, is_undercut = score_knock(
                        current_hand,
                        my_hand,
                        gin_bonus,
                        undercut_bonus,
                        knock_threshold,
                    )
                    # Negate: opponent scoring is bad for me
                    return RolloutResult(
                        my_points=-points,
                        is_draw=False,
                        i_knocked=False,
                        terminated_early=False,
                    )

        my_turn = not my_turn
        turns_played += 1

    # Hit max_turns -- evaluate with terminal heuristic
    heuristic_points = evaluate_terminal(my_hand, opp_hand, knock_threshold)
    return RolloutResult(
        my_points=heuristic_points,
        is_draw=False,
        i_knocked=False,
        terminated_early=True,
    )


# ---------------------------------------------------------------------------
# Module-level worker functions (required for pickling with ProcessPoolExecutor)
# ---------------------------------------------------------------------------


def _worker_init() -> None:
    """Seed random uniquely per worker process."""
    seed = os.getpid() * 31 + int(time.time() * 1000) % 1_000_000
    random.seed(seed)


def _sample_state(
    unknown: list[Card],
    opponent_known: list[Card],
) -> tuple[list[Card], list[Card]]:
    """Standalone sampling: shuffle unknown cards, partition into opp hand + deck.

    Returns:
        (opponent_hand, deck)
    """
    shuffled = list(unknown)
    random.shuffle(shuffled)

    opp_hand_size = 10
    fill_needed = max(0, opp_hand_size - len(opponent_known))
    fill_needed = min(fill_needed, len(shuffled))

    opp_hand = list(opponent_known) + shuffled[:fill_needed]
    deck = shuffled[fill_needed:]
    return opp_hand, deck


def _draw_sim_batch(
    option: str,
    my_hand: list[Card],
    discard_top: Card,
    sim_discard_base: list[Card],
    rollout_ai: BasicAI,
    max_turns: int,
    knock_threshold: int,
    gin_bonus: int,
    undercut_bonus: int,
    n_sims: int,
    samples: list[tuple[list[Card], list[Card]]] | None,
    unknown: list[Card] | None,
    opponent_known: list[Card] | None,
) -> int:
    """Run N draw simulations for one option ("deck" or "discard").

    Returns total points across all sims.
    """
    total = 0
    for i in range(n_sims):
        if samples is not None:
            opp_hand, sim_deck = samples[i]
        else:
            opp_hand, sim_deck = _sample_state(unknown, opponent_known)

        if option == "discard":
            sim_hand = list(my_hand) + [discard_top]
            discard_card = rollout_ai.decide_discard(Hand(sim_hand))
            sim_hand_after = [c for c in sim_hand if c != discard_card]
            sim_discard_after = [discard_card]
        else:  # deck
            deck_copy = list(sim_deck)
            if not deck_copy:
                continue
            drawn_card = deck_copy.pop()
            sim_hand = list(my_hand) + [drawn_card]
            discard_card = rollout_ai.decide_discard(Hand(sim_hand))
            sim_hand_after = [c for c in sim_hand if c != discard_card]
            sim_discard_after = list(sim_discard_base) + [discard_card]
            sim_deck = deck_copy  # use the deck with drawn card removed

        result = rollout(
            list(sim_hand_after), list(opp_hand), list(sim_deck),
            list(sim_discard_after), False, rollout_ai,
            max_turns, knock_threshold, gin_bonus, undercut_bonus,
        )
        total += result.my_points
    return total


def _discard_sim_batch(
    cards: list[Card],
    card_to_discard: Card,
    rollout_ai: BasicAI,
    max_turns: int,
    knock_threshold: int,
    gin_bonus: int,
    undercut_bonus: int,
    n_sims: int,
    samples: list[tuple[list[Card], list[Card]]] | None,
    unknown: list[Card] | None,
    opponent_known: list[Card] | None,
) -> int:
    """Run N discard simulations for one candidate card.

    Returns total points across all sims.
    """
    sim_hand = [c for c in cards if c != card_to_discard]
    total = 0
    for i in range(n_sims):
        if samples is not None:
            opp_hand, sim_deck = samples[i]
        else:
            opp_hand, sim_deck = _sample_state(unknown, opponent_known)

        sim_discard = [card_to_discard]
        result = rollout(
            list(sim_hand), list(opp_hand), list(sim_deck),
            list(sim_discard), False, rollout_ai,
            max_turns, knock_threshold, gin_bonus, undercut_bonus,
        )
        total += result.my_points
    return total


def _knock_sim_batch(
    option: str,
    my_hand: list[Card],
    rollout_ai: BasicAI,
    max_turns: int,
    knock_threshold: int,
    gin_bonus: int,
    undercut_bonus: int,
    n_sims: int,
    samples: list[tuple[list[Card], list[Card]]] | None,
    unknown: list[Card] | None,
    opponent_known: list[Card] | None,
) -> int:
    """Run N knock simulations for one option ("knock" or "continue").

    Returns total points across all sims.
    """
    total = 0
    for i in range(n_sims):
        if samples is not None:
            opp_hand, sim_deck = samples[i]
        else:
            opp_hand, sim_deck = _sample_state(unknown, opponent_known)

        if option == "knock":
            points, _, _ = score_knock(
                my_hand, list(opp_hand),
                gin_bonus, undercut_bonus, knock_threshold,
            )
            total += points
        else:  # continue
            result = rollout(
                list(my_hand), list(opp_hand), list(sim_deck),
                [], True, rollout_ai,
                max_turns, knock_threshold, gin_bonus, undercut_bonus,
            )
            total += result.my_points
    return total


class MonteCarloAI(ContextAwareAI):
    """AI that uses Monte Carlo rollouts to evaluate decisions.

    Extends ContextAwareAI (inherits opponent tracking and context building).
    For each decision point, samples possible hidden card distributions and
    runs simulated games to find the best option.
    """

    def __init__(self, config: Config | None = None) -> None:
        super().__init__(config)
        cfg = config or get_config()
        mc_cfg = cfg.monte_carlo_ai

        self.draw_simulations = mc_cfg.draw_simulations
        self.discard_simulations = mc_cfg.discard_simulations
        self.knock_simulations = mc_cfg.knock_simulations
        self.max_discard_candidates = mc_cfg.max_discard_candidates
        self.max_rollout_turns = mc_cfg.max_rollout_turns
        self.min_unknown_for_simulation = mc_cfg.min_unknown_for_simulation

        # Build rollout AI with conservative knock policy
        rollout_ai_config = replace(
            cfg.ai,
            knock_strategy=mc_cfg.rollout_knock_strategy,
            conservative_knock_threshold=mc_cfg.rollout_conservative_threshold,
        )
        rollout_config = replace(cfg, ai=rollout_ai_config)
        self._rollout_ai = BasicAI(rollout_config)

        # Confidence thresholds for fallback to heuristic
        self.draw_min_advantage = mc_cfg.draw_min_advantage
        self.discard_min_advantage = mc_cfg.discard_min_advantage
        self.knock_min_advantage = mc_cfg.knock_min_advantage

        # Game rules from config
        self._gin_bonus = cfg.game_rules.gin_bonus
        self._undercut_bonus = cfg.game_rules.undercut_bonus
        self._knock_threshold = cfg.game_rules.knock_threshold

        # Parallelization settings
        if mc_cfg.max_workers == 0:
            self._max_workers = max(1, (os.cpu_count() or 2) - 1)
        else:
            self._max_workers = max(1, mc_cfg.max_workers)
        self._sample_strategy = mc_cfg.sample_strategy
        self._pool: ProcessPoolExecutor | None = None

        # Last thinking data for UI display
        self.last_mc_thinking: dict[str, Any] | None = None

    def _get_pool(self) -> ProcessPoolExecutor | None:
        """Lazy-create a ProcessPoolExecutor, or return None if sequential."""
        if self._max_workers <= 1:
            return None
        if self._pool is None:
            self._pool = ProcessPoolExecutor(
                max_workers=self._max_workers,
                initializer=_worker_init,
            )
        return self._pool

    def _generate_samples(
        self,
        n: int,
        unknown: list[Card],
        opponent_known: set[Card],
    ) -> list[tuple[list[Card], list[Card]]]:
        """Pre-generate N (opp_hand, deck) samples for paired mode."""
        opp_known_list = list(opponent_known)
        samples = []
        for _ in range(n):
            opp_hand, deck = _sample_state(unknown, opp_known_list)
            samples.append((opp_hand, deck))
        return samples

    def _run_parallel(
        self,
        tasks: list[tuple[Any, ...]],
    ) -> list[int]:
        """Submit (fn, *args) tasks to the pool and collect results.

        If no pool (sequential mode), calls functions directly.
        """
        pool = self._get_pool()
        if pool is None:
            results = []
            for fn, *args in tasks:
                results.append(fn(*args))
            return results

        futures = []
        for fn, *args in tasks:
            futures.append(pool.submit(fn, *args))
        return [f.result() for f in futures]

    def shutdown(self) -> None:
        """Shut down the process pool if active."""
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None

    def __del__(self) -> None:
        self.shutdown()

    def _get_known_and_unknown(
        self, hand: Hand, context: GameContext | None = None
    ) -> tuple[set[Card], list[Card]]:
        """Build known/unknown card sets for information set sampling.

        Known locations: my hand, discard pile history, cards opponent picked up.
        Unknown: everything else in the 52-card deck.

        Returns:
            Tuple of (known_cards, unknown_cards_list).
        """
        known = set(hand)

        if context and context.known_cards:
            kc = context.known_cards
            known |= set(kc.discard_buried)
            if kc.discard_top:
                known.add(kc.discard_top)
            known |= set(kc.opponent_hand_known)

        if context and context.discard_history:
            known |= set(context.discard_history)

        unknown = [c for c in ALL_CARDS if c not in known]
        return known, unknown

    def _sample_game_state(
        self,
        my_hand: list[Card],
        unknown_cards: list[Card],
        opponent_known: set[Card],
        deck_remaining: int,
        discard_pile: list[Card],
    ) -> tuple[list[Card], list[Card], list[Card]]:
        """Sample a possible opponent hand and deck from unknown cards.

        Args:
            my_hand: My current hand.
            unknown_cards: Cards whose location is unknown.
            opponent_known: Cards known to be in opponent's hand.
            deck_remaining: Number of cards in the deck.
            discard_pile: Current discard pile.

        Returns:
            Tuple of (opponent_hand, deck, discard_pile_copy).
        """
        shuffled = list(unknown_cards)
        random.shuffle(shuffled)

        # Opponent hand: known cards + fill from unknown
        opp_known_list = list(opponent_known)
        opp_hand_size = 10  # Standard hand size
        fill_needed = max(0, opp_hand_size - len(opp_known_list))
        fill_needed = min(fill_needed, len(shuffled))

        opp_hand = opp_known_list + shuffled[:fill_needed]
        remaining = shuffled[fill_needed:]

        # Deck is the rest of the unknown cards
        deck = remaining

        return opp_hand, deck, list(discard_pile)

    def decide_draw(
        self,
        hand: Hand,
        discard_top: Card | None,
        context: GameContext | None = None,
    ) -> DrawChoice:
        """Monte Carlo draw decision: simulate both options and pick the best.

        Falls back to ContextAwareAI when too few unknown cards remain.
        """
        ctx = context or self._current_context

        if discard_top is None:
            return DrawChoice.DECK

        known, unknown = self._get_known_and_unknown(hand, ctx)

        if len(unknown) < self.min_unknown_for_simulation:
            return super().decide_draw(hand, discard_top, context)

        opponent_known = set()
        if ctx and ctx.known_cards:
            opponent_known = set(ctx.known_cards.opponent_hand_known)

        deck_remaining = ctx.deck_remaining if ctx else len(unknown)

        knock_threshold = self._knock_threshold
        if ctx and hasattr(ctx, 'knock_threshold'):
            knock_threshold = ctx.knock_threshold

        # For rollout discard pile, we only need the top (for drawing).
        # The full history is used for known/unknown tracking, not for the sim pile.
        sim_discard_base = [discard_top] if discard_top else []

        my_hand_list = list(hand)
        opp_known_list = list(opponent_known)

        # Build samples and tasks
        if self._sample_strategy == "paired":
            samples = self._generate_samples(
                self.draw_simulations, unknown, opponent_known,
            )
            ind_unknown = None
            ind_opp_known = None
        else:
            samples = None
            ind_unknown = unknown
            ind_opp_known = opp_known_list

        tasks: list[tuple[Any, ...]] = [
            (
                _draw_sim_batch, "discard", my_hand_list, discard_top,
                sim_discard_base, self._rollout_ai, self.max_rollout_turns,
                knock_threshold, self._gin_bonus, self._undercut_bonus,
                self.draw_simulations, samples, ind_unknown, ind_opp_known,
            ),
            (
                _draw_sim_batch, "deck", my_hand_list, discard_top,
                sim_discard_base, self._rollout_ai, self.max_rollout_turns,
                knock_threshold, self._gin_bonus, self._undercut_bonus,
                self.draw_simulations, samples, ind_unknown, ind_opp_known,
            ),
        ]

        results = self._run_parallel(tasks)
        discard_total, deck_total = results[0], results[1]

        deck_avg = deck_total / max(1, self.draw_simulations)
        discard_avg = discard_total / max(1, self.draw_simulations)

        advantage = abs(discard_avg - deck_avg)
        fallback = False

        # Confidence threshold: fall back to heuristic when signal is weak
        if advantage < self.draw_min_advantage:
            fallback = True
            choice = super().decide_draw(hand, discard_top, context)
        elif discard_avg > deck_avg:
            choice = DrawChoice.DISCARD
        else:
            choice = DrawChoice.DECK

        # Store thinking data
        draw_thinking = {
            'deck_avg_points': round(deck_avg, 1),
            'deck_sims': self.draw_simulations,
            'discard_avg_points': round(discard_avg, 1),
            'discard_sims': self.draw_simulations,
            'discard_card': str(discard_top),
            'choice': choice.name.lower(),
            'advantage': round(advantage, 1),
            'fallback': fallback,
        }

        # Initialize thinking dict for this turn
        self.last_mc_thinking = {'draw': draw_thinking, 'discard': None, 'knock': None}

        logger.info(
            "MC Draw: DECK avg=%.1f, DISCARD(%s) avg=%.1f, adv=%.1f%s -> %s",
            deck_avg, discard_top, discard_avg, advantage,
            " (fallback)" if fallback else "", choice.name,
        )

        return choice

    def decide_discard(self, hand: Hand) -> Card:
        """Monte Carlo discard decision: evaluate non-meld cards via simulation.

        Analyzes hand to find deadwood cards (not in any meld), then runs
        rollouts for each to find the best discard.
        """
        ctx = self._current_context
        known, unknown = self._get_known_and_unknown(hand, ctx)

        if len(unknown) < self.min_unknown_for_simulation:
            return super().decide_discard(hand)

        cards = list(hand)

        # Use the hand's cached analysis to find deadwood cards
        deadwood_cards = set(hand.analyze().deadwood_cards)

        candidates: list[tuple[Card, int]] = []
        for card in cards:
            if card not in deadwood_cards:
                continue
            remaining = [c for c in cards if c != card]
            dw = analyze_hand(remaining).deadwood_value
            candidates.append((card, dw))

        # Fallback: if all cards are in melds (rare with 11 cards), evaluate all
        if not candidates:
            for card in cards:
                remaining = [c for c in cards if c != card]
                dw = analyze_hand(remaining).deadwood_value
                candidates.append((card, dw))

        candidates.sort(key=lambda x: x[1])
        top_candidates = candidates

        opponent_known = set()
        if ctx and ctx.known_cards:
            opponent_known = set(ctx.known_cards.opponent_hand_known)

        deck_remaining = ctx.deck_remaining if ctx else len(unknown)

        knock_threshold = self._knock_threshold
        if ctx and hasattr(ctx, 'knock_threshold'):
            knock_threshold = ctx.knock_threshold

        opp_known_list = list(opponent_known)

        # Build samples and tasks
        if self._sample_strategy == "paired":
            samples = self._generate_samples(
                self.discard_simulations, unknown, opponent_known,
            )
            ind_unknown = None
            ind_opp_known = None
        else:
            samples = None
            ind_unknown = unknown
            ind_opp_known = opp_known_list

        tasks: list[tuple[Any, ...]] = []
        for card, immediate_dw in top_candidates:
            tasks.append((
                _discard_sim_batch, cards, card, self._rollout_ai,
                self.max_rollout_turns, knock_threshold,
                self._gin_bonus, self._undercut_bonus,
                self.discard_simulations, samples, ind_unknown, ind_opp_known,
            ))

        totals = self._run_parallel(tasks)

        # Process results
        candidate_results: list[dict[str, Any]] = []
        best_card = top_candidates[0][0]
        best_avg = float('-inf')

        for idx, (card, immediate_dw) in enumerate(top_candidates):
            avg_points = totals[idx] / max(1, self.discard_simulations)
            candidate_results.append({
                'card': str(card),
                'avg_points': round(avg_points, 1),
                'sims': self.discard_simulations,
                'deadwood_after': immediate_dw,
            })

            if avg_points > best_avg or (avg_points == best_avg and immediate_dw < candidates[0][1]):
                best_avg = avg_points
                best_card = card

        # Sort results by avg_points descending for display
        candidate_results.sort(key=lambda x: x['avg_points'], reverse=True)

        # Confidence threshold: if MC's best-to-second-best gap is small
        # AND MC disagrees with heuristic, defer to heuristic
        fallback = False
        if len(candidate_results) >= 2:
            best_to_second = candidate_results[0]['avg_points'] - candidate_results[1]['avg_points']
            heuristic_choice = super().decide_discard(hand)
            if best_to_second < self.discard_min_advantage and best_card != heuristic_choice:
                fallback = True
                best_card = heuristic_choice
        else:
            best_to_second = float('inf')

        discard_thinking = {
            'candidates': candidate_results,
            'chosen': str(best_card),
            'hand_size': len(cards),
            'deadwood_count': len(deadwood_cards),
            'fallback': fallback,
        }

        if self.last_mc_thinking is None:
            self.last_mc_thinking = {'draw': None, 'discard': None, 'knock': None}
        self.last_mc_thinking['discard'] = discard_thinking

        logger.info(
            "MC Discard: chose %s (avg=%.1f) from %d candidates%s",
            best_card, best_avg, len(top_candidates),
            " (fallback)" if fallback else "",
        )

        return best_card

    def should_knock(
        self, hand: Hand, context: GameContext | None = None
    ) -> bool:
        """Monte Carlo knock decision: compare knock vs continue via simulation."""
        deadwood = hand.deadwood_total

        # Always knock with gin
        if deadwood == 0:
            knock_thinking = {
                'knock_avg_points': None,
                'continue_avg_points': None,
                'chose_knock': True,
                'deadwood': 0,
                'reason': 'gin',
            }
            if self.last_mc_thinking is None:
                self.last_mc_thinking = {'draw': None, 'discard': None, 'knock': None}
            self.last_mc_thinking['knock'] = knock_thinking
            return True

        if deadwood > 10:
            return False

        ctx = context or self._current_context

        # Edge cases from parent: deck nearly empty, game-winning knock
        if ctx:
            if ctx.deck_remaining <= 4:
                knock_thinking = {
                    'knock_avg_points': None,
                    'continue_avg_points': None,
                    'chose_knock': True,
                    'deadwood': deadwood,
                    'reason': 'deck_nearly_empty',
                }
                if self.last_mc_thinking is None:
                    self.last_mc_thinking = {'draw': None, 'discard': None, 'knock': None}
                self.last_mc_thinking['knock'] = knock_thinking
                return True

            potential_points = 25 if deadwood == 0 else 10 - deadwood
            if ctx.my_score + potential_points >= ctx.target_score:
                knock_thinking = {
                    'knock_avg_points': None,
                    'continue_avg_points': None,
                    'chose_knock': True,
                    'deadwood': deadwood,
                    'reason': 'game_winning',
                }
                if self.last_mc_thinking is None:
                    self.last_mc_thinking = {'draw': None, 'discard': None, 'knock': None}
                self.last_mc_thinking['knock'] = knock_thinking
                return True

        known, unknown = self._get_known_and_unknown(hand, ctx)

        if len(unknown) < self.min_unknown_for_simulation:
            return super().should_knock(hand, context)

        opponent_known = set()
        if ctx and ctx.known_cards:
            opponent_known = set(ctx.known_cards.opponent_hand_known)

        deck_remaining = ctx.deck_remaining if ctx else len(unknown)

        knock_threshold = self._knock_threshold
        if ctx and hasattr(ctx, 'knock_threshold'):
            knock_threshold = ctx.knock_threshold

        my_hand_list = list(hand)
        opp_known_list = list(opponent_known)

        # Build samples and tasks
        if self._sample_strategy == "paired":
            samples = self._generate_samples(
                self.knock_simulations, unknown, opponent_known,
            )
            ind_unknown = None
            ind_opp_known = None
        else:
            samples = None
            ind_unknown = unknown
            ind_opp_known = opp_known_list

        tasks: list[tuple[Any, ...]] = [
            (
                _knock_sim_batch, "knock", my_hand_list, self._rollout_ai,
                self.max_rollout_turns, knock_threshold,
                self._gin_bonus, self._undercut_bonus,
                self.knock_simulations, samples, ind_unknown, ind_opp_known,
            ),
            (
                _knock_sim_batch, "continue", my_hand_list, self._rollout_ai,
                self.max_rollout_turns, knock_threshold,
                self._gin_bonus, self._undercut_bonus,
                self.knock_simulations, samples, ind_unknown, ind_opp_known,
            ),
        ]

        results = self._run_parallel(tasks)
        knock_total, continue_total = results[0], results[1]

        knock_avg = knock_total / max(1, self.knock_simulations)
        continue_avg = continue_total / max(1, self.knock_simulations)

        advantage = abs(knock_avg - continue_avg)
        fallback = False

        # Confidence threshold: fall back to heuristic when signal is weak
        if advantage < self.knock_min_advantage:
            fallback = True
            chose_knock = super().should_knock(hand, context)
        else:
            chose_knock = knock_avg > continue_avg

        knock_thinking = {
            'knock_avg_points': round(knock_avg, 1),
            'continue_avg_points': round(continue_avg, 1),
            'chose_knock': chose_knock,
            'deadwood': deadwood,
            'advantage': round(advantage, 1),
            'fallback': fallback,
        }

        if self.last_mc_thinking is None:
            self.last_mc_thinking = {'draw': None, 'discard': None, 'knock': None}
        self.last_mc_thinking['knock'] = knock_thinking

        logger.info(
            "MC Knock: knock_avg=%.1f, continue_avg=%.1f, adv=%.1f%s -> %s (deadwood=%d)",
            knock_avg, continue_avg, advantage,
            " (fallback)" if fallback else "",
            "KNOCK" if chose_knock else "CONTINUE", deadwood,
        )

        return chose_knock

    # --- Reasoning methods (compatible with existing DB pipeline) ---

    def decide_draw_with_reasoning(
        self,
        hand: Hand,
        discard_top: Card | None,
        context: GameContext | None = None,
    ) -> DrawReasoning:
        """Draw decision with MC reasoning data."""
        choice = self.decide_draw(hand, discard_top, context)

        factors = []
        reasoning_str = ""

        if self.last_mc_thinking and self.last_mc_thinking.get('draw'):
            dt = self.last_mc_thinking['draw']
            factors.append(f"MC draw sims: {dt['deck_sims']}")
            factors.append(f"DECK avg: {dt['deck_avg_points']}")
            factors.append(f"DISCARD avg: {dt['discard_avg_points']}")
            if dt.get('discard_card'):
                factors.append(f"Discard card: {dt['discard_card']}")
            reasoning_str = (
                f"MC: DECK avg={dt['deck_avg_points']}, "
                f"DISCARD({dt.get('discard_card', '?')}) avg={dt['discard_avg_points']} "
                f"-> {choice.name}"
            )
        else:
            reasoning_str = f"Drew from {choice.name} (fallback)"

        return DrawReasoning(
            choice=choice,
            reasoning=reasoning_str,
            factors=factors,
        )

    def decide_discard_with_reasoning(self, hand: Hand) -> DiscardReasoning:
        """Discard decision with MC reasoning data."""
        card = self.decide_discard(hand)

        factors = []
        options_str: list[tuple[str, int]] = []
        reasoning_str = ""

        if self.last_mc_thinking and self.last_mc_thinking.get('discard'):
            dd = self.last_mc_thinking['discard']
            factors.append(f"MC discard candidates: {len(dd['candidates'])}")
            factors.append(f"Deadwood cards: {dd.get('deadwood_count', len(dd['candidates']))}")
            for cand in dd['candidates']:
                options_str.append((cand['card'], cand['deadwood_after']))
                factors.append(
                    f"{cand['card']}: avg={cand['avg_points']}, dw={cand['deadwood_after']}"
                )
            reasoning_str = (
                f"MC: chose {dd['chosen']} from {len(dd['candidates'])} candidates"
            )
        else:
            reasoning_str = f"Discarded {card} (fallback)"

        return DiscardReasoning(
            card=card,
            reasoning=reasoning_str,
            factors=factors,
            options_considered=options_str,
        )

    def should_knock_with_reasoning(
        self, hand: Hand, context: GameContext | None = None
    ) -> KnockReasoning:
        """Knock decision with MC reasoning data."""
        result = self.should_knock(hand, context)

        factors = []
        score_val = None
        reasoning_str = ""

        if self.last_mc_thinking and self.last_mc_thinking.get('knock'):
            kt = self.last_mc_thinking['knock']
            factors.append(f"Deadwood: {kt['deadwood']}")

            if kt.get('reason'):
                factors.append(f"Reason: {kt['reason']}")
                reasoning_str = f"Knock ({kt['reason']}): deadwood={kt['deadwood']}"
            elif kt.get('knock_avg_points') is not None:
                factors.append(f"MC knock avg: {kt['knock_avg_points']}")
                factors.append(f"MC continue avg: {kt['continue_avg_points']}")
                score_val = kt['knock_avg_points']
                reasoning_str = (
                    f"MC: knock avg={kt['knock_avg_points']}, "
                    f"continue avg={kt['continue_avg_points']} "
                    f"-> {'KNOCK' if result else 'CONTINUE'}"
                )
            else:
                reasoning_str = f"{'Knocked' if result else 'No knock'}: deadwood={kt['deadwood']}"
        else:
            deadwood = hand.deadwood_total
            factors.append(f"Deadwood: {deadwood}")
            reasoning_str = f"{'Knocked' if result else 'No knock'}: deadwood={deadwood} (fallback)"

        return KnockReasoning(
            should_knock=result,
            reasoning=reasoning_str,
            score=score_val,
            factors=factors,
        )
