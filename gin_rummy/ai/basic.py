"""Basic AI opponent for Gin Rummy."""

from __future__ import annotations

import logging
from typing import ClassVar

from gin_rummy.ai.opponent_model import OpponentModel
from gin_rummy.ai.types import (
    DiscardReasoning,
    DrawChoice,
    DrawReasoning,
    KnockReasoning,
)
from gin_rummy.config import Config, get_config
from gin_rummy.models import Card, Hand, analyze_hand
from gin_rummy.models.game_context import GameContext

logger = logging.getLogger(__name__)


class BasicAI:
    """Basic AI opponent with configurable heuristics.

    Strategy (configurable via config.toml):
    - Draw from discard if the card improves hand by min_deadwood_improvement
    - Discard highest deadwood card not contributing to melds
    - Knock based on knock_strategy ("always" or "conservative")

    BasicAI is also the base class and *the* AI interface: every AI accepts
    the same arguments (an optional GameContext everywhere, plus
    pending_discard on should_knock) and supports opponent tracking via
    record_opponent_* / reset_for_new_hand. Callers never need to check the
    concrete class. Subclasses that actually read the context set
    ``needs_context = True`` so the runner builds one for them; a decision
    never falls back to a stored context, so a missing one is visible.
    """

    needs_context: ClassVar[bool] = False

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

        # Opponent tracking. BasicAI itself ignores both, but keeping them on
        # the base class means every AI can be fed the same events.
        self.opponent_model = OpponentModel()

    # ---- Shared interface: opponent tracking ----

    def record_opponent_discard(self, card: Card) -> None:
        """Record that the opponent discarded a card."""
        self.opponent_model.record_discard(card)

    def record_opponent_pickup(self, card: Card) -> None:
        """Record that the opponent picked up a card from the discard pile."""
        self.opponent_model.record_pickup(card)

    def reset_for_new_hand(self) -> None:
        """Forget per-hand tracking state."""
        self.opponent_model.reset()

    def shutdown(self) -> None:
        """Release external resources (worker pools). No-op for most AIs."""

    # ---- Decisions ----
    #
    # Each decision has ONE implementation (`_evaluate_*`) that returns the
    # choice plus the raw numbers behind it. The plain method returns the
    # choice; the *_with_reasoning twin formats those numbers. BasicAI is the
    # Monte Carlo rollout AI, so the plain path builds no strings.

    def _knock_threshold_for(self, context: GameContext | None) -> int:
        """The knock threshold in effect (dynamic under Oklahoma Gin)."""
        return context.knock_threshold if context is not None else self.knock_threshold

    # -- draw --

    def decide_draw(self, hand: Hand, discard_top: Card | None, context: GameContext | None = None) -> DrawChoice:
        """Decide whether to draw from deck or discard pile."""
        return self._evaluate_draw(hand, discard_top, context)[0]

    def decide_draw_with_reasoning(
        self, hand: Hand, discard_top: Card | None, context: GameContext | None = None
    ) -> DrawReasoning:
        """Draw decision with the reasoning behind it."""
        choice, current_deadwood, reason = self._evaluate_draw(hand, discard_top, context)
        factors = [f"Current deadwood: {current_deadwood}"]
        if discard_top is None:
            return DrawReasoning(choice=choice, reasoning="Drew from DECK: discard pile empty", factors=factors)
        factors += [f"Discard top: {discard_top}", reason]
        if choice == DrawChoice.DISCARD:
            return DrawReasoning(choice=choice, reasoning=f"Drew {discard_top} from DISCARD: {reason}", factors=factors)
        return DrawReasoning(
            choice=choice, reasoning=f"Drew from DECK: {discard_top} doesn't help ({reason})", factors=factors
        )

    def _evaluate_draw(
        self, hand: Hand, discard_top: Card | None, context: GameContext | None = None
    ) -> tuple[DrawChoice, int, str]:
        """Returns (choice, current deadwood, one-line reason)."""
        current_deadwood = hand.deadwood_total
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Draw decision: current hand %s (deadwood=%d)", [str(c) for c in hand], current_deadwood)

        if discard_top is None:
            logger.info("Draw decision: DECK (discard pile empty)")
            return DrawChoice.DECK, current_deadwood, "discard pile empty"

        helps, reason = self._card_helps_hand(hand, discard_top, context)
        if helps:
            logger.info("Draw decision: DISCARD - taking %s (%s)", discard_top, reason)
            return DrawChoice.DISCARD, current_deadwood, reason
        logger.info("Draw decision: DECK - %s doesn't help (%s)", discard_top, reason)
        return DrawChoice.DECK, current_deadwood, reason

    def _card_helps_hand(self, hand: Hand, card: Card, context: GameContext | None = None) -> tuple[bool, str]:
        """Check if a card would help the hand form melds.

        Coordinates with decide_discard so we never pick up a card only to
        discard it immediately.

        Returns:
            Tuple of (helps: bool, reason: str explaining the decision).
        """
        current_deadwood = hand.analyze().deadwood_value

        # Add the card to simulate picking it up, then see what we would
        # ACTUALLY discard (subclasses record nothing while _in_hypothetical)
        test_hand = Hand(list(hand) + [card])
        self._in_hypothetical = True
        try:
            would_discard = self.decide_discard(test_hand, context)
        finally:
            self._in_hypothetical = False

        if would_discard == card:
            return False, f"would immediately discard {card} - wastes turn"

        remaining = [c for c in test_hand if c != would_discard]
        new_deadwood = analyze_hand(remaining).deadwood_value
        improvement = current_deadwood - new_deadwood
        if improvement >= self.min_deadwood_improvement:
            return True, f"reduces deadwood from {current_deadwood} to {new_deadwood} by discarding {would_discard}"
        return False, f"improvement {improvement} < required {self.min_deadwood_improvement}"

    # -- discard --

    def decide_discard(self, hand: Hand, context: GameContext | None = None) -> Card:
        """Discard the card that leaves the lowest deadwood."""
        best, best_deadwood, options = self._rank_discards(hand)
        logger.info("Discard decision: %s (leaves deadwood=%d, best of %d options)", best, best_deadwood, len(options))
        return best

    def decide_discard_with_reasoning(self, hand: Hand, context: GameContext | None = None) -> DiscardReasoning:
        """Discard decision with the reasoning behind it."""
        best, best_deadwood, options = self._rank_discards(hand)
        return DiscardReasoning(
            card=best,
            reasoning=f"Discarded {best}: leaves deadwood={best_deadwood} (best of {len(options)} options)",
            factors=[f"Hand size: {len(options)} cards", f"Best resulting deadwood: {best_deadwood}"],
            options_considered=[(str(c), dw) for c, dw in options[:5]],
        )

    def _rank_discards(self, hand: Hand) -> tuple[Card, int, list[tuple[Card, int]]]:
        """Try every discard. Returns (best card, its resulting deadwood, all options sorted by deadwood).

        Ties go to the card that appears first in the hand.
        """
        cards = list(hand)
        best: Card | None = None
        best_deadwood = float("inf")
        options: list[tuple[Card, int]] = []
        for i, card in enumerate(cards):
            deadwood = analyze_hand(cards[:i] + cards[i + 1 :]).deadwood_value
            options.append((card, deadwood))
            if deadwood < best_deadwood:
                best_deadwood = deadwood
                best = card
        options.sort(key=lambda x: x[1])
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Discard options (card -> resulting deadwood): %s", [(str(c), dw) for c, dw in options])
        if best is None:  # empty hand; keep the old fallback semantics
            best = max(cards, key=lambda c: c.deadwood_value)
        return best, int(best_deadwood), options

    # -- knock --

    def should_knock(self, hand: Hand, context: GameContext | None = None, pending_discard: Card | None = None) -> bool:
        """Decide whether to knock based on the configured strategy."""
        return self._evaluate_knock(hand, context)[0]

    def should_knock_with_reasoning(
        self, hand: Hand, context: GameContext | None = None, pending_discard: Card | None = None
    ) -> KnockReasoning:
        """Knock decision with the reasoning behind it."""
        should_knock, code, deadwood, threshold = self._evaluate_knock(hand, context)
        factors = [f"Deadwood: {deadwood}", f"Strategy: {self.knock_strategy}"]
        cons = self.conservative_knock_threshold
        if code == "gin":
            factors.append("GIN achieved!")
            reasoning = "Knocked: GIN! (deadwood=0)"
        elif code == "cannot":
            factors.append(f"Cannot knock: deadwood > {threshold}")
            reasoning = f"No knock: deadwood={deadwood} > {threshold}"
        elif code == "always":
            factors.append("Strategy=always: knock when able")
            reasoning = f"Knocked: deadwood={deadwood} (strategy=always)"
        elif code == "conservative_yes":
            factors.append(f"Conservative: {deadwood} <= {cons}")
            reasoning = f"Knocked: deadwood={deadwood} <= {cons} (strategy=conservative)"
        elif code == "conservative_no":
            factors.append(f"Conservative: {deadwood} > {cons}")
            reasoning = f"No knock: deadwood={deadwood} > {cons} (strategy=conservative)"
        else:
            factors.append(f"Unknown strategy '{self.knock_strategy}', defaulting to knock")
            reasoning = f"Knocked: deadwood={deadwood} (unknown strategy, default=always)"
        return KnockReasoning(should_knock=should_knock, reasoning=reasoning, score=None, factors=factors)

    def _evaluate_knock(self, hand: Hand, context: GameContext | None) -> tuple[bool, str, int, int]:
        """Returns (should_knock, verdict code, deadwood, threshold in effect)."""
        deadwood = hand.deadwood_total
        threshold = self._knock_threshold_for(context)
        if deadwood == 0:
            logger.info("Knock decision: YES - GIN! (deadwood=0)")
            return True, "gin", deadwood, threshold
        if deadwood > threshold:
            logger.debug("Knock decision: NO (deadwood=%d > %d, cannot knock)", deadwood, threshold)
            return False, "cannot", deadwood, threshold
        if self.knock_strategy == "always":
            logger.info("Knock decision: YES (deadwood=%d, strategy=always)", deadwood)
            return True, "always", deadwood, threshold
        if self.knock_strategy == "conservative":
            if deadwood <= self.conservative_knock_threshold:
                logger.info(
                    "Knock decision: YES (deadwood=%d <= %d, strategy=conservative)",
                    deadwood,
                    self.conservative_knock_threshold,
                )
                return True, "conservative_yes", deadwood, threshold
            logger.info(
                "Knock decision: NO (deadwood=%d > %d, strategy=conservative)",
                deadwood,
                self.conservative_knock_threshold,
            )
            return False, "conservative_no", deadwood, threshold
        logger.warning("Unknown knock strategy '%s', defaulting to always knock", self.knock_strategy)
        return True, "unknown", deadwood, threshold
