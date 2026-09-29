"""Rollout simulation: play a sampled position forward and score it."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.types import (
    DrawChoice,
)
from gin_rummy.models import Card, Hand, Rank, Suit, analyze_hand
from gin_rummy.models.melds import calculate_layoff

if TYPE_CHECKING:
    pass


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


# Extra own-deadwood a defensive rollout discard will accept to avoid
# feeding the other side's melds
_DEFENSIVE_SLACK = 2


def _rollout_discard(
    current_hand: list[Card],
    other_hand: list[Card],
    rollout_ai: BasicAI,
    defensive: bool,
) -> Card:
    """Pick a rollout discard, optionally avoiding cards the other side wants.

    Rollout hands are determinized (both visible), so with `defensive` we
    can check exactly whether a candidate discard would improve the other
    hand's melds, and prefer a safe discard within _DEFENSIVE_SLACK
    deadwood of the greedy-best choice.
    """
    if not defensive:
        return rollout_ai.decide_discard(Hand(current_hand))

    ranked: list[tuple[int, Card]] = []
    for i, card in enumerate(current_hand):
        remaining = current_hand[:i] + current_hand[i + 1 :]
        ranked.append((analyze_hand(remaining).deadwood_value, card))
    ranked.sort(key=lambda x: x[0])

    best_dw = ranked[0][0]
    other_dw = analyze_hand(other_hand).deadwood_value

    for dw, card in ranked:
        if dw > best_dw + _DEFENSIVE_SLACK:
            break
        # benefit > 0 means the card melds into (or improves) the other hand
        # rather than sitting there as extra deadwood
        benefit = (other_dw + card.deadwood_value) - analyze_hand(other_hand + [card]).deadwood_value
        if benefit <= 0:
            return card

    # Every acceptable candidate feeds the other hand - take the greedy best
    return ranked[0][1]


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
    min_deck_cards: int = 2,
    defensive: bool = False,
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
        current_hand = my_hand if my_turn else opp_hand

        # Draw decision
        discard_top = discard_pile[-1] if discard_pile else None
        hand_obj = Hand(current_hand)
        draw_choice = rollout_ai.decide_draw(hand_obj, discard_top)

        # Execute draw. Matching the engine, the round only ends in a draw
        # when a DECK draw is attempted at the minimum - taking the discard
        # remains legal regardless of deck size.
        if draw_choice == DrawChoice.DISCARD and discard_pile:
            drawn = discard_pile.pop()
        else:
            if len(deck) <= min_deck_cards:
                return RolloutResult(my_points=0, is_draw=True, i_knocked=False, terminated_early=False)
            drawn = deck.pop()
        current_hand.append(drawn)

        # Discard decision
        other_hand = opp_hand if my_turn else my_hand
        discard_card = _rollout_discard(current_hand, other_hand, rollout_ai, defensive)
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
