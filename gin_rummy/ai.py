"""AI opponent for Gin Rummy."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from gin_rummy.models import Card, Suit, Rank, Hand, analyze_hand, find_all_melds
from gin_rummy.config import get_config, Config

if TYPE_CHECKING:
    from gin_rummy.context import GameContext


logger = logging.getLogger(__name__)


class DrawChoice(Enum):
    """AI's choice of where to draw from."""
    DECK = auto()
    DISCARD = auto()


@dataclass
class AIDecision:
    """Container for AI's turn decisions."""
    draw_from: DrawChoice
    discard: Card
    should_knock: bool


class BasicAI:
    """Basic AI opponent with configurable heuristics.

    Strategy (configurable via config.toml):
    - Draw from discard if the card improves hand by min_deadwood_improvement
    - Discard highest deadwood card not contributing to melds
    - Knock based on knock_strategy ("always" or "conservative")
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize AI with settings from config.

        Args:
            config: Optional config override. If None, uses global config.
        """
        cfg = config or get_config()
        self.knock_strategy = cfg.ai.knock_strategy
        self.conservative_knock_threshold = cfg.ai.conservative_knock_threshold
        self.min_deadwood_improvement = cfg.ai.min_deadwood_improvement

    def decide_draw(self, hand: Hand, discard_top: Card | None) -> DrawChoice:
        """Decide whether to draw from deck or discard pile.

        Args:
            hand: Current hand.
            discard_top: Top card of discard pile, or None if empty.

        Returns:
            DrawChoice indicating where to draw from.
        """
        current_deadwood = hand.deadwood_total
        logger.debug(
            "Draw decision: current hand %s (deadwood=%d)",
            [str(c) for c in hand],
            current_deadwood,
        )

        if discard_top is None:
            logger.info("Draw decision: DECK (discard pile empty)")
            return DrawChoice.DECK

        # Check if taking the discard would improve our hand
        helps, reason = self._card_helps_hand(hand, discard_top)
        if helps:
            logger.info(
                "Draw decision: DISCARD - taking %s (%s)",
                discard_top,
                reason,
            )
            return DrawChoice.DISCARD

        logger.info(
            "Draw decision: DECK - %s doesn't help (%s)",
            discard_top,
            reason,
        )
        return DrawChoice.DECK

    def _card_helps_hand(self, hand: Hand, card: Card) -> tuple[bool, str]:
        """Check if a card would help the hand form melds.

        CRITICAL FIX: This method now coordinates with decide_discard to ensure
        we don't pick up a card only to immediately discard it.

        Args:
            hand: Current hand.
            card: Card to evaluate.

        Returns:
            Tuple of (helps: bool, reason: str explaining the decision).
        """
        current_analysis = hand.analyze()
        current_deadwood = current_analysis.deadwood_value

        # Add the card to simulate picking it up
        test_hand = Hand(list(hand) + [card])

        # Use decide_discard to see what we would ACTUALLY discard
        # This ensures coordination between draw and discard decisions
        would_discard = self.decide_discard(test_hand)

        # CRITICAL CHECK: Never pick up a card if we'd immediately discard it!
        if would_discard == card:
            reason = f"would immediately discard {card} - wastes turn"
            return False, reason

        # Calculate the deadwood after discarding what we actually would discard
        remaining = [c for c in test_hand if c != would_discard]
        analysis = analyze_hand(remaining)
        new_deadwood = analysis.deadwood_value

        # Take the card if it reduces deadwood by enough
        improvement = current_deadwood - new_deadwood
        if improvement >= self.min_deadwood_improvement:
            reason = (
                f"reduces deadwood from {current_deadwood} to {new_deadwood} "
                f"by discarding {would_discard}"
            )
            return True, reason
        else:
            reason = (
                f"improvement {improvement} < required {self.min_deadwood_improvement}"
            )
            return False, reason

    def decide_discard(self, hand: Hand) -> Card:
        """Decide which card to discard.

        Args:
            hand: Current hand (should have 11 cards after drawing).

        Returns:
            Card to discard.
        """
        cards = list(hand)
        best_discard = None
        best_deadwood = float('inf')
        discard_options: list[tuple[Card, int]] = []

        # Try discarding each card and see which leaves lowest deadwood
        for i, card in enumerate(cards):
            remaining = cards[:i] + cards[i+1:]
            analysis = analyze_hand(remaining)
            discard_options.append((card, analysis.deadwood_value))
            if analysis.deadwood_value < best_deadwood:
                best_deadwood = analysis.deadwood_value
                best_discard = card

        # Log all options considered
        discard_options.sort(key=lambda x: x[1])
        logger.debug(
            "Discard options (card -> resulting deadwood): %s",
            [(str(c), dw) for c, dw in discard_options],
        )

        # Fallback: discard highest value card
        if best_discard is None:
            best_discard = max(cards, key=lambda c: c.deadwood_value)
            logger.info(
                "Discard decision: %s (fallback - highest deadwood value card)",
                best_discard,
            )
        else:
            logger.info(
                "Discard decision: %s (leaves deadwood=%d, best of %d options)",
                best_discard,
                int(best_deadwood),
                len(cards),
            )

        return best_discard

    def should_knock(self, hand: Hand) -> bool:
        """Decide whether to knock based on configured strategy.

        Args:
            hand: Current hand (should have 10 cards).

        Returns:
            True if AI should knock.
        """
        deadwood = hand.deadwood_total
        can_knock = deadwood <= 10
        is_gin = deadwood == 0

        if is_gin:
            logger.info("Knock decision: YES - GIN! (deadwood=0)")
            return True
        elif not can_knock:
            logger.debug(
                "Knock decision: NO (deadwood=%d > 10, cannot knock)",
                deadwood,
            )
            return False
        elif self.knock_strategy == "always":
            logger.info(
                "Knock decision: YES (deadwood=%d, strategy=always)",
                deadwood,
            )
            return True
        elif self.knock_strategy == "conservative":
            if deadwood <= self.conservative_knock_threshold:
                logger.info(
                    "Knock decision: YES (deadwood=%d <= %d, strategy=conservative)",
                    deadwood,
                    self.conservative_knock_threshold,
                )
                return True
            else:
                logger.info(
                    "Knock decision: NO (deadwood=%d > %d, strategy=conservative)",
                    deadwood,
                    self.conservative_knock_threshold,
                )
                return False
        else:
            # Unknown strategy, default to always knock
            logger.warning(
                "Unknown knock strategy '%s', defaulting to always knock",
                self.knock_strategy,
            )
            return True

    def make_turn_decision(
        self,
        hand: Hand,
        discard_top: Card | None,
        drawn_card: Card,
    ) -> tuple[Card, bool]:
        """Make discard and knock decisions after drawing.

        Args:
            hand: Hand after drawing (11 cards).
            discard_top: What was on top of discard (for context).
            drawn_card: The card that was drawn.

        Returns:
            Tuple of (card to discard, whether to knock).
        """
        logger.debug("--- AI Turn Start ---")
        logger.debug("Drew: %s", drawn_card)

        discard = self.decide_discard(hand)

        # Check if we can knock after discarding
        test_cards = [c for c in hand if c != discard]
        test_analysis = analyze_hand(test_cards)
        can_knock = test_analysis.deadwood_value <= 10

        should_knock = can_knock and self.should_knock(Hand(test_cards))

        logger.debug(
            "--- AI Turn End --- (discard=%s, knock=%s)",
            discard,
            should_knock,
        )

        return discard, should_knock


class ContextAwareAI(BasicAI):
    """AI that adjusts strategy based on game context.

    Extends BasicAI with:
    - Dynamic draw threshold based on deck position, outs, and score
    - Opponent pattern tracking to predict discards/takes
    - Meld-completing out detection for smarter draw decisions
    - Denial play (taking cards opponent wants)

    All parameters are configurable via config.toml [context_aware_ai] section.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize with context-aware components.

        Args:
            config: Optional config override. If None, uses global config.
        """
        super().__init__(config)

        # Import here to avoid circular imports
        from gin_rummy.context import (
            OutsCalculator,
            OpponentModel,
            DynamicThresholdCalculator,
        )

        cfg = config or get_config()
        self.context_config = cfg.context_aware_ai

        self.outs_calculator = OutsCalculator(self.context_config)
        self.opponent_model = OpponentModel()
        self.threshold_calculator = DynamicThresholdCalculator(self.context_config)

        # Current game context (updated each turn)
        self._current_context: GameContext | None = None

    def update_context(self, context: GameContext) -> None:
        """Update the current game context.

        Should be called at the start of each turn with fresh context.

        Args:
            context: Current game state snapshot.
        """
        self._current_context = context

        # Calculate outs for this hand
        if context.my_outs is None:
            # Need to get hand from somewhere - context should have it
            # For now, outs will be calculated in decide_draw
            pass

    def record_opponent_discard(self, card: Card) -> None:
        """Record that opponent discarded a card.

        Args:
            card: The card opponent discarded.
        """
        if self.context_config.track_opponent_patterns:
            self.opponent_model.record_discard(card)

    def record_opponent_pickup(self, card: Card) -> None:
        """Record that opponent picked up from discard.

        Args:
            card: The card opponent picked up.
        """
        if self.context_config.track_opponent_patterns:
            self.opponent_model.record_pickup(card)

    def reset_for_new_hand(self) -> None:
        """Reset tracking for a new hand."""
        self.opponent_model.reset()
        self._current_context = None

    def decide_draw(
        self,
        hand: Hand,
        discard_top: Card | None,
        context: GameContext | None = None,
    ) -> DrawChoice:
        """Context-aware draw decision.

        If context is provided, uses dynamic threshold and outs analysis.
        Otherwise falls back to BasicAI behavior.

        Args:
            hand: Current hand.
            discard_top: Top card of discard pile, or None if empty.
            context: Optional game context for smarter decisions.

        Returns:
            DrawChoice indicating where to draw from.
        """
        # Use provided context or fall back to stored context
        ctx = context or self._current_context

        # Fall back to BasicAI if no context
        if ctx is None:
            logger.debug("ContextAwareAI: No context, falling back to BasicAI")
            return super().decide_draw(hand, discard_top)

        if discard_top is None:
            logger.info("Draw decision: DECK (discard pile empty)")
            return DrawChoice.DECK

        # Calculate outs for this hand
        outs_analysis = self.outs_calculator.calculate_outs(
            hand,
            dead_cards=ctx.dead_cards,
            deck_position_pct=ctx.deck_position_pct,
        )
        ctx.my_outs = outs_analysis

        # Calculate dynamic threshold
        threshold = self.threshold_calculator.calculate_threshold(ctx)

        # Calculate base improvement (same as BasicAI)
        current_deadwood = hand.deadwood_total
        helps, reason = self._card_helps_hand(hand, discard_top)

        # Calculate improvement value
        improvement = 0.0
        if helps:
            # Extract improvement from reason string or recalculate
            test_cards = list(hand) + [discard_top]
            best_new_deadwood = float('inf')
            for i, candidate in enumerate(test_cards):
                remaining = test_cards[:i] + test_cards[i + 1 :]
                analysis = analyze_hand(remaining)
                if analysis.deadwood_value < best_new_deadwood:
                    best_new_deadwood = analysis.deadwood_value
            improvement = current_deadwood - best_new_deadwood

        # Denial bonus: take if opponent wants it badly
        opponent_want_prob = self.opponent_model.predict_will_take(discard_top)
        if opponent_want_prob >= self.context_config.denial_probability_threshold:
            improvement += self.context_config.denial_bonus
            logger.debug(
                "Denial bonus: +%d (opponent want prob=%.2f)",
                self.context_config.denial_bonus,
                opponent_want_prob,
            )

        # Make decision
        if improvement >= threshold:
            logger.info(
                "Draw decision: DISCARD - taking %s (improvement=%.1f >= threshold=%d, "
                "outs=%d live)",
                discard_top,
                improvement,
                threshold,
                outs_analysis.live_out_count,
            )
            return DrawChoice.DISCARD
        else:
            logger.info(
                "Draw decision: DECK - %s (improvement=%.1f < threshold=%d, "
                "deck_pos=%.0f%%, outs=%d live)",
                discard_top,
                improvement,
                threshold,
                ctx.deck_position_pct * 100,
                outs_analysis.live_out_count,
            )
            return DrawChoice.DECK

    def decide_discard(self, hand: Hand) -> Card:
        """Context-aware discard decision with safety scoring.

        Extends BasicAI's deadwood-minimizing logic with:
        - Bonus for discarding "safe" ranks (opponent discarded same rank)
        - Penalty for discarding "dangerous" ranks (opponent picked up same rank)
        - Penalty for discarding "dangerous" suits (opponent picked up same suit)
        - Consideration of live outs (prefer keeping cards with live potential melds)

        Args:
            hand: Current hand (should have 11 cards after drawing).

        Returns:
            Card to discard.
        """
        cards = list(hand)
        best_discard = None
        best_score = float('inf')  # Lower is better
        discard_options: list[tuple[Card, float, int, str]] = []

        # Get context for dead cards calculation
        ctx = self._current_context
        dead_cards = ctx.dead_cards if ctx else set()
        deck_position = ctx.deck_position_pct if ctx else 0.0

        # Find cards in melds - only penalize if discarding would break a 3-card meld
        current_analysis = hand.analyze()
        cards_in_3card_melds = set()
        for meld in current_analysis.melds:
            if len(meld.cards) == 3:
                # 3-card meld: discarding would break it entirely
                cards_in_3card_melds.update(meld.cards)
            # 4+ card melds: OK to discard (still leaves valid 3-card meld)

        for i, card in enumerate(cards):
            remaining = cards[:i] + cards[i + 1 :]
            analysis = analyze_hand(remaining)

            # Base score is resulting deadwood (lower = better)
            deadwood = analysis.deadwood_value
            score = float(deadwood)
            flags: list[str] = []

            # Calculate live outs for the remaining hand
            # Prefer discards that leave more live outs (cards with meld potential)
            if self.context_config.live_outs_discard_weight > 0:
                remaining_hand = Hand(remaining)
                outs_analysis = self.outs_calculator.calculate_outs(
                    remaining_hand, dead_cards, deck_position
                )
                # Lower score is better, so subtract based on weighted out value
                # More/better outs = lower score = better to keep that hand
                # Use weighted_value to account for strategic importance of different out types
                live_outs_bonus = (
                    outs_analysis.weighted_value
                    * self.context_config.live_outs_discard_weight
                )
                score -= live_outs_bonus
                if outs_analysis.live_out_count > 0:
                    flags.append(f"outs={outs_analysis.live_out_count},wv={outs_analysis.weighted_value:.1f}")

            # Apply safety bonus (reduce score for safe discards)
            if self.opponent_model.is_rank_safe(card.rank):
                score -= self.context_config.safe_rank_discard_bonus
                flags.append("safe")

            # Apply danger penalties (increase score for dangerous discards)
            # Check specific meld completion first (most precise signal)
            if self.opponent_model.is_card_dangerous(card):
                score += self.context_config.danger_card_penalty
                flags.append("completes_meld")
            else:
                # Fall back to general rank/suit danger (less precise)
                if self.opponent_model.is_rank_dangerous(card.rank):
                    score += self.context_config.dangerous_rank_penalty
                    flags.append("dangerous_rank")

                if self.opponent_model.is_suit_dangerous(card.suit):
                    score += self.context_config.dangerous_suit_penalty
                    flags.append("dangerous_suit")

            # MASSIVE penalty for discarding from 3-card melds (would break them)
            # 4+ card melds are allowed (strategic play for gin attempts)
            if card in cards_in_3card_melds:
                score += 100  # Huge penalty for breaking 3-card melds
                flags.append("IN_3CARD_MELD!")

            flag_str = ",".join(flags) if flags else ""
            discard_options.append((card, score, deadwood, flag_str))

            if score < best_score:
                best_score = score
                best_discard = card

        # Log all options considered
        discard_options.sort(key=lambda x: x[1])
        logger.debug(
            "Discard options (card -> score, deadwood, flags): %s",
            [(str(c), f"{s:.1f}", dw, f) for c, s, dw, f in discard_options],
        )

        # Fallback (shouldn't happen)
        if best_discard is None:
            best_discard = max(cards, key=lambda c: c.deadwood_value)
            logger.info(
                "Discard decision: %s (fallback - highest deadwood value card)",
                best_discard,
            )
        else:
            # Find the chosen option's details
            chosen = next(
                (opt for opt in discard_options if opt[0] == best_discard), None
            )
            if chosen:
                _, score, deadwood, flags = chosen
                flag_str = f" [{flags}]" if flags else ""
                logger.info(
                    "Discard decision: %s (score=%.1f, deadwood=%d%s)",
                    best_discard,
                    score,
                    deadwood,
                    flag_str,
                )

        return best_discard


def _card_to_index(card: Card) -> int:
    """Convert a Card to an index 0-51 for statistics tracking."""
    suit_idx = list(Suit).index(card.suit)
    rank_idx = list(Rank).index(card.rank)
    return suit_idx * 13 + rank_idx


def _deadwood_bucket(deadwood: int) -> str:
    """Get deadwood bucket for draw statistics."""
    if deadwood <= 10:
        return "0-10"
    elif deadwood <= 20:
        return "11-20"
    elif deadwood <= 30:
        return "21-30"
    else:
        return "31+"


class StatisticalAI(BasicAI):
    """AI that learns from experience by tracking action outcomes.

    Tracks statistics for:
    - Card discards: which cards lead to wins/losses
    - Draw decisions: when drawing from discard helps
    - Knock decisions: optimal deadwood threshold for knocking

    Statistics persist to a JSON file and improve over many games.
    Falls back to BasicAI logic when insufficient data exists.
    """

    # Minimum samples before using statistical decision
    MIN_SAMPLES = 20

    def __init__(
        self,
        stats_path: Path | str | None = None,
        config: Config | None = None,
    ) -> None:
        """Initialize Statistical AI.

        Args:
            stats_path: Path to JSON file for persisting statistics.
            config: Optional config override.
        """
        super().__init__(config)

        if stats_path is not None:
            self.stats_path = Path(stats_path)
        else:
            self.stats_path = None

        # Statistics storage
        # Card discard stats: card_index -> {times, wins, points}
        self.discard_stats: dict[int, dict[str, int]] = {}

        # Draw stats: bucket -> {deck_draws, deck_wins, discard_draws, discard_wins}
        self.draw_stats: dict[str, dict[str, int]] = {}

        # Knock stats: deadwood -> {knocked, knock_wins, continued, continue_wins}
        self.knock_stats: dict[int, dict[str, int]] = {}

        # Track decisions made this round (for updating after outcome)
        self._round_discards: list[int] = []  # card indices discarded
        self._round_draws: list[tuple[str, str]] = []  # (bucket, "deck"|"discard")
        self._round_knocks: list[tuple[int, bool]] = []  # (deadwood, did_knock)

        # Load existing stats
        if self.stats_path and self.stats_path.exists():
            self.load()

    def reset_for_new_hand(self) -> None:
        """Reset tracking for a new hand."""
        self._round_discards = []
        self._round_draws = []
        self._round_knocks = []

    def decide_draw(self, hand: Hand, discard_top: Card | None) -> DrawChoice:
        """Use statistics to decide draw, with BasicAI fallback.

        Args:
            hand: Current hand.
            discard_top: Top card of discard pile, or None if empty.

        Returns:
            DrawChoice indicating where to draw from.
        """
        if discard_top is None:
            return DrawChoice.DECK

        bucket = _deadwood_bucket(hand.deadwood_total)
        stats = self.draw_stats.get(bucket)

        # Check if we have enough data
        if stats is None or (stats.get("deck_draws", 0) + stats.get("discard_draws", 0)) < self.MIN_SAMPLES:
            # Fall back to BasicAI
            choice = super().decide_draw(hand, discard_top)
        else:
            # Calculate win rates
            deck_draws = stats.get("deck_draws", 0)
            deck_wins = stats.get("deck_wins", 0)
            discard_draws = stats.get("discard_draws", 0)
            discard_wins = stats.get("discard_wins", 0)

            deck_rate = deck_wins / deck_draws if deck_draws > 0 else 0.5
            discard_rate = discard_wins / discard_draws if discard_draws > 0 else 0.5

            # Also check if the discard card itself would help (BasicAI logic)
            helps, _ = self._card_helps_hand(hand, discard_top)

            # Probabilistic selection based on win rates
            # Only consider discard if the card actually helps the hand
            if helps:
                # Use softmax-style probability: P(discard) = discard_rate / (deck_rate + discard_rate)
                total_rate = deck_rate + discard_rate
                if total_rate > 0:
                    discard_prob = discard_rate / total_rate
                else:
                    discard_prob = 0.5
                choice = DrawChoice.DISCARD if random.random() < discard_prob else DrawChoice.DECK
            else:
                # Card doesn't help - usually draw from deck, but still use probability
                # Bias toward deck when card doesn't help
                total_rate = deck_rate + discard_rate
                if total_rate > 0:
                    discard_prob = discard_rate / total_rate * 0.5  # Halve probability when card doesn't help
                else:
                    discard_prob = 0.25
                choice = DrawChoice.DISCARD if random.random() < discard_prob else DrawChoice.DECK

            logger.info(
                "Draw decision: %s (bucket=%s, deck_rate=%.2f, discard_rate=%.2f, helps=%s)",
                choice.name,
                bucket,
                deck_rate,
                discard_rate,
                helps,
            )

        # Record decision for later update
        self._round_draws.append((bucket, "discard" if choice == DrawChoice.DISCARD else "deck"))

        return choice

    def decide_discard(self, hand: Hand) -> Card:
        """Use statistics to influence discard decision.

        Blends BasicAI's deadwood analysis with historical win rates.

        Args:
            hand: Current hand (11 cards after drawing).

        Returns:
            Card to discard.
        """
        cards = list(hand)
        best_discard = None
        best_score = float("-inf")
        options: list[tuple[Card, float, int, float]] = []

        for i, card in enumerate(cards):
            remaining = cards[:i] + cards[i + 1:]
            analysis = analyze_hand(remaining)
            deadwood = analysis.deadwood_value

            # Base score: lower deadwood is better (negate so higher = better)
            base_score = -deadwood

            # Adjust by historical win rate for this card
            card_idx = _card_to_index(card)
            card_stats = self.discard_stats.get(card_idx)

            if card_stats and card_stats.get("times", 0) >= 10:
                times = card_stats["times"]
                wins = card_stats.get("wins", 0)
                win_rate = wins / times

                # Cards with LOW win rate when discarded are BAD to discard
                # So we want to discard cards with HIGH win rate
                # Adjust score: bonus for high win rate cards
                win_adjustment = (win_rate - 0.5) * 20  # ±10 point swing
            else:
                win_rate = 0.5
                win_adjustment = 0

            score = base_score + win_adjustment
            options.append((card, score, deadwood, win_rate))

            if score > best_score:
                best_score = score
                best_discard = card

        # Fallback
        if best_discard is None:
            best_discard = max(cards, key=lambda c: c.deadwood_value)

        # Log decision
        options.sort(key=lambda x: -x[1])
        logger.info(
            "Discard decision: %s (score=%.1f, top3=%s)",
            best_discard,
            best_score,
            [(str(c), f"dw={dw},wr={wr:.2f}") for c, _, dw, wr in options[:3]],
        )

        # Record for later update
        self._round_discards.append(_card_to_index(best_discard))

        return best_discard

    def should_knock(self, hand: Hand) -> bool:
        """Use statistics to decide whether to knock.

        Args:
            hand: Current hand (10 cards).

        Returns:
            True if AI should knock.
        """
        deadwood = hand.deadwood_total

        # Always knock with gin
        if deadwood == 0:
            self._round_knocks.append((0, True))
            return True

        # Can't knock if deadwood > 10
        if deadwood > 10:
            return False

        stats = self.knock_stats.get(deadwood)

        if stats is None or (stats.get("knocked", 0) + stats.get("continued", 0)) < self.MIN_SAMPLES:
            # Fall back to BasicAI
            decision = super().should_knock(hand)
        else:
            knocked = stats.get("knocked", 0)
            knock_wins = stats.get("knock_wins", 0)
            continued = stats.get("continued", 0)
            continue_wins = stats.get("continue_wins", 0)

            knock_rate = knock_wins / knocked if knocked > 0 else 0.5
            continue_rate = continue_wins / continued if continued > 0 else 0.5

            decision = knock_rate >= continue_rate

            logger.info(
                "Knock decision: %s (dw=%d, knock_rate=%.2f, continue_rate=%.2f)",
                "YES" if decision else "NO",
                deadwood,
                knock_rate,
                continue_rate,
            )

        # Record decision
        self._round_knocks.append((deadwood, decision))

        return decision

    def record_round_outcome(self, won: bool, points: int) -> None:
        """Update statistics based on round outcome.

        Should be called after each round with the result.

        Args:
            won: Whether this AI won the round.
            points: Points scored (positive if won, negative if lost).
        """
        win_val = 1 if won else 0

        # Update discard stats
        for card_idx in self._round_discards:
            if card_idx not in self.discard_stats:
                self.discard_stats[card_idx] = {"times": 0, "wins": 0, "points": 0}
            self.discard_stats[card_idx]["times"] += 1
            self.discard_stats[card_idx]["wins"] += win_val
            self.discard_stats[card_idx]["points"] += points

        # Update draw stats
        for bucket, choice in self._round_draws:
            if bucket not in self.draw_stats:
                self.draw_stats[bucket] = {
                    "deck_draws": 0, "deck_wins": 0,
                    "discard_draws": 0, "discard_wins": 0
                }
            if choice == "deck":
                self.draw_stats[bucket]["deck_draws"] += 1
                self.draw_stats[bucket]["deck_wins"] += win_val
            else:
                self.draw_stats[bucket]["discard_draws"] += 1
                self.draw_stats[bucket]["discard_wins"] += win_val

        # Update knock stats
        for deadwood, did_knock in self._round_knocks:
            if deadwood not in self.knock_stats:
                self.knock_stats[deadwood] = {
                    "knocked": 0, "knock_wins": 0,
                    "continued": 0, "continue_wins": 0
                }
            if did_knock:
                self.knock_stats[deadwood]["knocked"] += 1
                self.knock_stats[deadwood]["knock_wins"] += win_val
            else:
                self.knock_stats[deadwood]["continued"] += 1
                self.knock_stats[deadwood]["continue_wins"] += win_val

        # Clear round tracking
        self.reset_for_new_hand()

    def save(self) -> None:
        """Save statistics to JSON file."""
        if self.stats_path is None:
            return

        self.stats_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "discard_stats": {str(k): v for k, v in self.discard_stats.items()},
            "draw_stats": self.draw_stats,
            "knock_stats": {str(k): v for k, v in self.knock_stats.items()},
        }

        with open(self.stats_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.debug("Saved statistics to %s", self.stats_path)

    def load(self) -> None:
        """Load statistics from JSON file."""
        if self.stats_path is None or not self.stats_path.exists():
            return

        try:
            with open(self.stats_path) as f:
                data = json.load(f)

            self.discard_stats = {int(k): v for k, v in data.get("discard_stats", {}).items()}
            self.draw_stats = data.get("draw_stats", {})
            self.knock_stats = {int(k): v for k, v in data.get("knock_stats", {}).items()}

            total_samples = sum(s.get("times", 0) for s in self.discard_stats.values())
            logger.info("Loaded statistics from %s (%d samples)", self.stats_path, total_samples)

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load statistics: %s", e)

    def get_stats_summary(self) -> dict:
        """Get a summary of current statistics for debugging."""
        total_discards = sum(s.get("times", 0) for s in self.discard_stats.values())
        total_draws = sum(
            s.get("deck_draws", 0) + s.get("discard_draws", 0)
            for s in self.draw_stats.values()
        )
        total_knocks = sum(
            s.get("knocked", 0) + s.get("continued", 0)
            for s in self.knock_stats.values()
        )

        return {
            "total_discard_samples": total_discards,
            "total_draw_samples": total_draws,
            "total_knock_samples": total_knocks,
            "cards_with_data": len(self.discard_stats),
        }
