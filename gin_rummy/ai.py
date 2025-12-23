"""AI opponent for Gin Rummy."""

import logging
from dataclasses import dataclass
from enum import Enum, auto

from gin_rummy.card import Card, Suit, Rank
from gin_rummy.config import get_config
from gin_rummy.hand import Hand
from gin_rummy.melds import analyze_hand, find_all_melds


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

    def __init__(self) -> None:
        """Initialize AI with settings from config."""
        config = get_config()
        self.knock_strategy = config.ai.knock_strategy
        self.conservative_knock_threshold = config.ai.conservative_knock_threshold
        self.min_deadwood_improvement = config.ai.min_deadwood_improvement

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
