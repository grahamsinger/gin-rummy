"""Basic AI opponent for Gin Rummy."""

from __future__ import annotations

import logging

from gin_rummy.models import Card, Hand, analyze_hand
from gin_rummy.config import get_config, Config
from gin_rummy.ai.types import (
    DrawChoice,
    DrawReasoning,
    DiscardReasoning,
    KnockReasoning,
)


logger = logging.getLogger(__name__)


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
        self.knock_threshold = cfg.game_rules.knock_threshold

        # True while decide_discard is being called on a hypothetical hand
        # (from _card_helps_hand); lets subclasses skip side effects like
        # recording statistics for discards that never happen
        self._in_hypothetical = False

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
        self._in_hypothetical = True
        try:
            would_discard = self.decide_discard(test_hand)
        finally:
            self._in_hypothetical = False

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
        can_knock = deadwood <= self.knock_threshold
        is_gin = deadwood == 0

        if is_gin:
            logger.info("Knock decision: YES - GIN! (deadwood=0)")
            return True
        elif not can_knock:
            logger.debug(
                "Knock decision: NO (deadwood=%d > %d, cannot knock)",
                deadwood,
                self.knock_threshold,
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

    def decide_draw_with_reasoning(
        self, hand: Hand, discard_top: Card | None
    ) -> DrawReasoning:
        """Decide where to draw with detailed reasoning.

        Args:
            hand: Current hand.
            discard_top: Top card of discard pile, or None if empty.

        Returns:
            DrawReasoning with choice, reasoning string, and factors.
        """
        current_deadwood = hand.deadwood_total
        factors: list[str] = [f"Current deadwood: {current_deadwood}"]

        if discard_top is None:
            return DrawReasoning(
                choice=DrawChoice.DECK,
                reasoning="Drew from DECK: discard pile empty",
                factors=factors,
            )

        # Check if taking the discard would improve our hand
        helps, reason = self._card_helps_hand(hand, discard_top)

        if helps:
            # Parse the improvement from reason
            factors.append(f"Discard top: {discard_top}")
            factors.append(reason)
            return DrawReasoning(
                choice=DrawChoice.DISCARD,
                reasoning=f"Drew {discard_top} from DISCARD: {reason}",
                factors=factors,
            )

        factors.append(f"Discard top: {discard_top}")
        factors.append(reason)
        return DrawReasoning(
            choice=DrawChoice.DECK,
            reasoning=f"Drew from DECK: {discard_top} doesn't help ({reason})",
            factors=factors,
        )

    def decide_discard_with_reasoning(self, hand: Hand) -> DiscardReasoning:
        """Decide which card to discard with detailed reasoning.

        Args:
            hand: Current hand (should have 11 cards after drawing).

        Returns:
            DiscardReasoning with card, reasoning string, factors, and options.
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

        # Sort options by resulting deadwood
        discard_options.sort(key=lambda x: x[1])

        # Convert to string format for the dataclass
        options_str = [(str(c), dw) for c, dw in discard_options]

        factors: list[str] = []
        factors.append(f"Hand size: {len(cards)} cards")
        factors.append(f"Best resulting deadwood: {int(best_deadwood)}")

        # Fallback: discard highest value card
        if best_discard is None:
            best_discard = max(cards, key=lambda c: c.deadwood_value)
            return DiscardReasoning(
                card=best_discard,
                reasoning=f"Discarded {best_discard}: fallback to highest deadwood value",
                factors=factors,
                options_considered=options_str[:5],  # Top 5 options
            )

        return DiscardReasoning(
            card=best_discard,
            reasoning=f"Discarded {best_discard}: leaves deadwood={int(best_deadwood)} (best of {len(cards)} options)",
            factors=factors,
            options_considered=options_str[:5],  # Top 5 options
        )

    def should_knock_with_reasoning(self, hand: Hand) -> KnockReasoning:
        """Decide whether to knock with detailed reasoning.

        Args:
            hand: Current hand (should have 10 cards).

        Returns:
            KnockReasoning with decision, reasoning string, and factors.
        """
        deadwood = hand.deadwood_total
        can_knock = deadwood <= self.knock_threshold
        is_gin = deadwood == 0

        factors: list[str] = [f"Deadwood: {deadwood}"]
        factors.append(f"Strategy: {self.knock_strategy}")

        if is_gin:
            factors.append("GIN achieved!")
            return KnockReasoning(
                should_knock=True,
                reasoning="Knocked: GIN! (deadwood=0)",
                score=None,
                factors=factors,
            )

        if not can_knock:
            factors.append(f"Cannot knock: deadwood > {self.knock_threshold}")
            return KnockReasoning(
                should_knock=False,
                reasoning=f"No knock: deadwood={deadwood} > {self.knock_threshold}",
                score=None,
                factors=factors,
            )

        if self.knock_strategy == "always":
            factors.append("Strategy=always: knock when able")
            return KnockReasoning(
                should_knock=True,
                reasoning=f"Knocked: deadwood={deadwood} (strategy=always)",
                score=None,
                factors=factors,
            )

        if self.knock_strategy == "conservative":
            if deadwood <= self.conservative_knock_threshold:
                factors.append(f"Conservative: {deadwood} <= {self.conservative_knock_threshold}")
                return KnockReasoning(
                    should_knock=True,
                    reasoning=(
                        f"Knocked: deadwood={deadwood} <= {self.conservative_knock_threshold} "
                        "(strategy=conservative)"
                    ),
                    score=None,
                    factors=factors,
                )
            else:
                factors.append(f"Conservative: {deadwood} > {self.conservative_knock_threshold}")
                return KnockReasoning(
                    should_knock=False,
                    reasoning=(
                        f"No knock: deadwood={deadwood} > {self.conservative_knock_threshold} "
                        "(strategy=conservative)"
                    ),
                    score=None,
                    factors=factors,
                )

        # Unknown strategy, default to always knock
        factors.append(f"Unknown strategy '{self.knock_strategy}', defaulting to knock")
        return KnockReasoning(
            should_knock=True,
            reasoning=f"Knocked: deadwood={deadwood} (unknown strategy, default=always)",
            score=None,
            factors=factors,
        )

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
        can_knock = test_analysis.deadwood_value <= self.knock_threshold

        should_knock = can_knock and self.should_knock(Hand(test_cards))

        logger.debug(
            "--- AI Turn End --- (discard=%s, knock=%s)",
            discard,
            should_knock,
        )

        return discard, should_knock
