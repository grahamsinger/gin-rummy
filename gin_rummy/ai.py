"""AI opponent for Gin Rummy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
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

        Args:
            hand: Current hand.
            card: Card to evaluate.

        Returns:
            Tuple of (helps: bool, reason: str explaining the decision).
        """
        current_analysis = hand.analyze()
        current_deadwood = current_analysis.deadwood_value

        # Add the card and find best discard
        test_cards = list(hand) + [card]

        # Find what our deadwood would be with each possible discard
        best_new_deadwood = float('inf')
        best_discard_for_new: Card | None = None
        for i, discard_candidate in enumerate(test_cards):
            remaining = test_cards[:i] + test_cards[i+1:]
            analysis = analyze_hand(remaining)
            if analysis.deadwood_value < best_new_deadwood:
                best_new_deadwood = analysis.deadwood_value
                best_discard_for_new = discard_candidate

        # Take the card if it reduces our best possible deadwood by enough
        improvement = current_deadwood - best_new_deadwood
        if improvement >= self.min_deadwood_improvement:
            reason = (
                f"reduces deadwood from {current_deadwood} to {int(best_new_deadwood)} "
                f"by discarding {best_discard_for_new}"
            )
            return True, reason
        else:
            reason = (
                f"improvement {int(improvement)} < required {self.min_deadwood_improvement}"
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

        # Key out bonus: meld-completing cards get bonus
        is_key_out = discard_top in outs_analysis.live_meld_completing_cards
        if is_key_out:
            improvement += self.context_config.key_out_bonus
            logger.debug(
                "Key out bonus: +%d for meld-completing card %s",
                self.context_config.key_out_bonus,
                discard_top,
            )

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
                "key_out=%s, outs=%d live)",
                discard_top,
                improvement,
                threshold,
                is_key_out,
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

        Args:
            hand: Current hand (should have 11 cards after drawing).

        Returns:
            Card to discard.
        """
        cards = list(hand)
        best_discard = None
        best_score = float('inf')  # Lower is better
        discard_options: list[tuple[Card, float, int, str]] = []

        for i, card in enumerate(cards):
            remaining = cards[:i] + cards[i + 1 :]
            analysis = analyze_hand(remaining)

            # Base score is resulting deadwood (lower = better)
            deadwood = analysis.deadwood_value
            score = float(deadwood)
            flags: list[str] = []

            # Apply safety bonus (reduce score for safe discards)
            if self.opponent_model.is_rank_safe(card.rank):
                score -= self.context_config.safe_rank_discard_bonus
                flags.append("safe")

            # Apply danger penalties (increase score for dangerous discards)
            if self.opponent_model.is_rank_dangerous(card.rank):
                score += self.context_config.dangerous_rank_penalty
                flags.append("dangerous_rank")

            if self.opponent_model.is_suit_dangerous(card.suit):
                score += self.context_config.dangerous_suit_penalty
                flags.append("dangerous_suit")

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
