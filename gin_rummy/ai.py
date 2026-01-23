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


@dataclass
class DrawReasoning:
    """Reasoning for a draw decision."""
    choice: DrawChoice
    reasoning: str  # e.g., "Took Q♠ from discard: reduces deadwood by 8"
    factors: list[str]


@dataclass
class DiscardReasoning:
    """Reasoning for a discard decision."""
    card: Card
    reasoning: str  # e.g., "Discarded 7♥: highest deadwood, no meld potential"
    factors: list[str]
    options_considered: list[tuple[str, int]]  # [(card_str, deadwood), ...]


@dataclass
class KnockReasoning:
    """Reasoning for a knock decision."""
    should_knock: bool
    reasoning: str  # e.g., "Knocked with score 0.65"
    score: float | None  # knock score (for context-aware AI)
    factors: list[str]


@dataclass
class TurnReasoning:
    """Complete reasoning for an AI turn."""
    draw: DrawReasoning
    discard: DiscardReasoning
    knock: KnockReasoning | None = None


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
        can_knock = deadwood <= 10
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
            factors.append("Cannot knock: deadwood > 10")
            return KnockReasoning(
                should_knock=False,
                reasoning=f"No knock: deadwood={deadwood} > 10",
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
                    reasoning=f"Knocked: deadwood={deadwood} <= {self.conservative_knock_threshold} (strategy=conservative)",
                    score=None,
                    factors=factors,
                )
            else:
                factors.append(f"Conservative: {deadwood} > {self.conservative_knock_threshold}")
                return KnockReasoning(
                    should_knock=False,
                    reasoning=f"No knock: deadwood={deadwood} > {self.conservative_knock_threshold} (strategy=conservative)",
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
        """Draw decision - delegates to BasicAI for now.

        Context-aware draw logic was found to underperform BasicAI's simpler
        approach. This delegates directly to BasicAI until better heuristics
        are developed.

        Args:
            hand: Current hand.
            discard_top: Top card of discard pile, or None if empty.
            context: Optional game context (currently unused).

        Returns:
            DrawChoice indicating where to draw from.
        """
        # Delegate to BasicAI's proven draw logic
        return super().decide_draw(hand, discard_top)

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

    def should_knock(
        self, hand: Hand, context: GameContext | None = None
    ) -> bool:
        """Context-aware knock decision.

        Calculates a knock score from multiple factors:
        - Base score from deadwood (lower = higher score)
        - Gin pursuit modifier (wait for gin when close?)
        - Undercut risk modifier (opponent looks strong?)
        - Deck urgency modifier (deck running out?)
        - Score pressure modifier (game situation?)
        - Opponent strength modifier (opponent deadwood estimate)

        Args:
            hand: Current hand (should have 10 cards).
            context: Optional game context. If None, falls back to BasicAI.

        Returns:
            True if AI should knock.
        """
        deadwood = hand.deadwood_total
        is_gin = deadwood == 0

        # Edge case 1: Always knock with gin
        if is_gin:
            logger.info("Knock decision: YES - GIN!")
            return True

        # Can't knock if deadwood > 10
        if deadwood > 10:
            logger.debug("Knock decision: NO (deadwood=%d > 10)", deadwood)
            return False

        # Use stored context if not provided
        ctx = context or self._current_context

        # Fall back to BasicAI if no context or context-knock disabled
        if ctx is None or not self.context_config.use_context_knock:
            logger.debug("Knock decision: falling back to BasicAI")
            return super().should_knock(hand)

        # Edge case 2: Always knock if deck nearly empty (avoid draw)
        if ctx.deck_remaining <= 4:
            logger.info(
                "Knock decision: YES (deck nearly empty, %d cards remain)",
                ctx.deck_remaining,
            )
            return True

        # Edge case 3: Always knock if it would win the game
        if ctx.my_score + (25 if deadwood == 0 else 10 - deadwood) >= ctx.target_score:
            logger.info("Knock decision: YES (game-winning knock)")
            return True

        # Calculate knock score
        knock_score = self._calculate_knock_score(hand, ctx)

        # Make decision
        should_knock = knock_score >= self.context_config.knock_decision_threshold

        logger.info(
            "Knock decision: %s (score=%.2f, threshold=%.2f, deadwood=%d)",
            "YES" if should_knock else "NO",
            knock_score,
            self.context_config.knock_decision_threshold,
            deadwood,
        )

        return should_knock

    def _calculate_knock_score(self, hand: Hand, context: GameContext) -> float:
        """Calculate knock score from multiple factors.

        Args:
            hand: Current hand.
            context: Game context.

        Returns:
            Knock score from 0.0 to 1.0+ (can exceed 1.0 with bonuses).
        """
        deadwood = hand.deadwood_total
        factors: list[str] = []

        # Base score: (10 - deadwood) / 10 → lower deadwood = higher score
        base_score = (10 - deadwood) / 10.0
        factors.append(f"base={base_score:.2f}")

        score = base_score

        # Gin pursuit modifier: wait for gin when close?
        if deadwood <= self.context_config.gin_pursuit_threshold:
            pursue_gin, gin_prob = self._should_pursue_gin(hand, context)
            if pursue_gin:
                gin_modifier = -self.context_config.gin_pursuit_weight
                score += gin_modifier
                factors.append(f"gin_pursuit={gin_modifier:.2f}(prob={gin_prob:.2f})")

        # Undercut risk modifier: opponent looks strong?
        threat_level = self.opponent_model.estimate_threat_level(context)
        if threat_level >= self.context_config.undercut_risk_threshold:
            undercut_modifier = (
                -self.context_config.undercut_risk_weight * threat_level
            )
            score += undercut_modifier
            factors.append(f"undercut_risk={undercut_modifier:.2f}(threat={threat_level:.2f})")

        # Deck urgency modifier: knock as deck empties
        deck_remaining_pct = 1.0 - context.deck_position_pct
        if deck_remaining_pct < self.context_config.late_game_knock_threshold:
            # Urgency increases as deck empties
            urgency = 1.0 - (
                deck_remaining_pct / self.context_config.late_game_knock_threshold
            )
            urgency_modifier = self.context_config.deck_urgency_weight * urgency
            score += urgency_modifier
            factors.append(f"urgency={urgency_modifier:.2f}(deck={deck_remaining_pct:.0%})")

        # Score pressure modifier
        score_modifier = 0.0
        points_to_win = context.points_to_win
        opp_points_to_win = context.opponent_points_to_win

        # Game-winning potential
        if points_to_win <= 10 - deadwood:
            score_modifier += 0.5
            factors.append("game_winning=+0.5")
        # Opponent close to winning
        elif opp_points_to_win <= 15:
            score_modifier += 0.3
            factors.append("opp_close=+0.3")
        # Trailing significantly
        elif context.score_differential < -self.context_config.knock_trailing_threshold:
            score_modifier += 0.2
            factors.append("trailing=+0.2")
        # Leading significantly
        elif context.score_differential > self.context_config.knock_leading_threshold:
            score_modifier -= 0.2
            factors.append("leading=-0.2")

        score += score_modifier

        # Opponent strength modifier
        estimated_opp_deadwood = self.opponent_model.estimate_deadwood(context)
        if estimated_opp_deadwood >= self.context_config.opponent_high_deadwood_threshold:
            # Opponent weak - good time to knock
            score += 0.3
            factors.append(f"opp_weak=+0.3(est_dw={estimated_opp_deadwood})")
        elif estimated_opp_deadwood <= self.context_config.opponent_low_deadwood_threshold:
            # Opponent strong - risky to knock
            score -= 0.2
            factors.append(f"opp_strong=-0.2(est_dw={estimated_opp_deadwood})")

        logger.debug("Knock score factors: %s", ", ".join(factors))

        return score

    def _should_pursue_gin(
        self, hand: Hand, context: GameContext
    ) -> tuple[bool, float]:
        """Determine if we should wait for gin instead of knocking.

        Args:
            hand: Current hand with low deadwood (1-3).
            context: Game context.

        Returns:
            Tuple of (should_pursue: bool, gin_probability: float).
        """
        deadwood = hand.deadwood_total

        if deadwood == 0:
            # Already gin!
            return False, 1.0

        if deadwood > self.context_config.gin_pursuit_threshold:
            # Too far from gin
            return False, 0.0

        # Calculate outs for gin
        if context.my_outs is None:
            outs_analysis = self.outs_calculator.calculate_outs(
                hand,
                dead_cards=context.dead_cards,
                deck_position_pct=context.deck_position_pct,
            )
        else:
            outs_analysis = context.my_outs

        # Count live meld-completing outs
        live_outs = outs_analysis.live_out_count

        # Estimate probability of hitting gin
        # Rough estimate: live_outs / remaining_unknown_cards
        unknown_cards = max(1, context.deck_remaining)
        gin_probability = min(1.0, live_outs / unknown_cards)

        # Simple expected value calculation
        # EV(knock) = 10 - deadwood (assuming no undercut)
        # EV(gin) = gin_prob * 25 + (1 - gin_prob) * (10 - deadwood)
        ev_knock = 10 - deadwood
        ev_gin = gin_probability * 25 + (1 - gin_probability) * ev_knock

        should_pursue = (
            gin_probability >= self.context_config.min_gin_probability
            and ev_gin > ev_knock
        )

        logger.debug(
            "Gin pursuit: prob=%.2f, EV(knock)=%d, EV(gin)=%.1f, pursue=%s",
            gin_probability,
            ev_knock,
            ev_gin,
            should_pursue,
        )

        return should_pursue, gin_probability

    def make_turn_decision(
        self,
        hand: Hand,
        discard_top: Card | None,
        drawn_card: Card,
        context: GameContext | None = None,
    ) -> tuple[Card, bool]:
        """Make discard and knock decisions after drawing.

        Extends BasicAI to pass context to should_knock.

        Args:
            hand: Hand after drawing (11 cards).
            discard_top: What was on top of discard (for context).
            drawn_card: The card that was drawn.
            context: Optional game context.

        Returns:
            Tuple of (card to discard, whether to knock).
        """
        logger.debug("--- ContextAwareAI Turn Start ---")
        logger.debug("Drew: %s", drawn_card)

        # Use provided context or stored context
        ctx = context or self._current_context

        discard = self.decide_discard(hand)

        # Check if we can knock after discarding
        test_cards = [c for c in hand if c != discard]
        test_hand = Hand(test_cards)
        test_analysis = test_hand.analyze()
        can_knock = test_analysis.deadwood_value <= 10

        # Use context-aware knock decision
        should_knock = can_knock and self.should_knock(test_hand, ctx)

        logger.debug(
            "--- ContextAwareAI Turn End --- (discard=%s, knock=%s)",
            discard,
            should_knock,
        )

        return discard, should_knock

    def decide_draw_with_reasoning(
        self,
        hand: Hand,
        discard_top: Card | None,
        context: GameContext | None = None,
    ) -> DrawReasoning:
        """Context-aware draw decision with detailed reasoning.

        Currently delegates to BasicAI as context-aware draw was found to underperform.

        Args:
            hand: Current hand.
            discard_top: Top card of discard pile, or None if empty.
            context: Optional game context (currently unused).

        Returns:
            DrawReasoning with choice, reasoning string, and factors.
        """
        # Delegate to BasicAI's proven draw logic
        return super().decide_draw_with_reasoning(hand, discard_top)

    def decide_discard_with_reasoning(self, hand: Hand) -> DiscardReasoning:
        """Context-aware discard decision with detailed reasoning.

        Extends BasicAI's reasoning with safety scoring and live outs analysis.

        Args:
            hand: Current hand (should have 11 cards after drawing).

        Returns:
            DiscardReasoning with card, reasoning string, factors, and options.
        """
        cards = list(hand)
        best_discard = None
        best_score = float('inf')  # Lower is better
        discard_options: list[tuple[Card, float, int, str]] = []

        # Get context for dead cards calculation
        ctx = self._current_context
        dead_cards = ctx.dead_cards if ctx else set()
        deck_position = ctx.deck_position_pct if ctx else 0.0

        # Find cards in melds
        current_analysis = hand.analyze()
        cards_in_3card_melds = set()
        for meld in current_analysis.melds:
            if len(meld.cards) == 3:
                cards_in_3card_melds.update(meld.cards)

        for i, card in enumerate(cards):
            remaining = cards[:i] + cards[i + 1:]
            analysis = analyze_hand(remaining)

            # Base score is resulting deadwood (lower = better)
            deadwood = analysis.deadwood_value
            score = float(deadwood)
            flags: list[str] = []

            # Calculate live outs for the remaining hand
            if self.context_config.live_outs_discard_weight > 0:
                remaining_hand = Hand(remaining)
                outs_analysis = self.outs_calculator.calculate_outs(
                    remaining_hand, dead_cards, deck_position
                )
                live_outs_bonus = (
                    outs_analysis.weighted_value
                    * self.context_config.live_outs_discard_weight
                )
                score -= live_outs_bonus
                if outs_analysis.live_out_count > 0:
                    flags.append(f"outs={outs_analysis.live_out_count}")

            # Apply safety scoring
            if self.opponent_model.is_rank_safe(card.rank):
                score -= self.context_config.safe_rank_discard_bonus
                flags.append("safe")

            if self.opponent_model.is_card_dangerous(card):
                score += self.context_config.danger_card_penalty
                flags.append("dangerous")
            else:
                if self.opponent_model.is_rank_dangerous(card.rank):
                    score += self.context_config.dangerous_rank_penalty
                    flags.append("risky_rank")
                if self.opponent_model.is_suit_dangerous(card.suit):
                    score += self.context_config.dangerous_suit_penalty
                    flags.append("risky_suit")

            if card in cards_in_3card_melds:
                score += 100
                flags.append("IN_MELD")

            flag_str = ",".join(flags) if flags else ""
            discard_options.append((card, score, deadwood, flag_str))

            if score < best_score:
                best_score = score
                best_discard = card

        # Sort options by score
        discard_options.sort(key=lambda x: x[1])

        # Convert to string format for the dataclass
        options_str = [(str(c), dw) for c, _, dw, _ in discard_options[:5]]

        factors: list[str] = []
        factors.append(f"Hand size: {len(cards)} cards")

        # Fallback
        if best_discard is None:
            best_discard = max(cards, key=lambda c: c.deadwood_value)
            return DiscardReasoning(
                card=best_discard,
                reasoning=f"Discarded {best_discard}: fallback to highest deadwood value",
                factors=factors,
                options_considered=options_str,
            )

        # Find the chosen option's details
        chosen = next((opt for opt in discard_options if opt[0] == best_discard), None)
        if chosen:
            _, score, deadwood, flags = chosen
            flag_str = f" [{flags}]" if flags else ""
            factors.append(f"Score: {score:.1f}")
            factors.append(f"Resulting deadwood: {deadwood}")
            if flags:
                factors.append(f"Flags: {flags}")

            return DiscardReasoning(
                card=best_discard,
                reasoning=f"Discarded {best_discard}: score={score:.1f}, deadwood={deadwood}{flag_str}",
                factors=factors,
                options_considered=options_str,
            )

        return DiscardReasoning(
            card=best_discard,
            reasoning=f"Discarded {best_discard}",
            factors=factors,
            options_considered=options_str,
        )

    def should_knock_with_reasoning(
        self, hand: Hand, context: GameContext | None = None
    ) -> KnockReasoning:
        """Context-aware knock decision with detailed reasoning.

        Args:
            hand: Current hand (should have 10 cards).
            context: Optional game context. If None, falls back to BasicAI.

        Returns:
            KnockReasoning with decision, reasoning string, score, and factors.
        """
        deadwood = hand.deadwood_total
        is_gin = deadwood == 0

        factors: list[str] = [f"Deadwood: {deadwood}"]

        # Edge case 1: Always knock with gin
        if is_gin:
            factors.append("GIN achieved!")
            return KnockReasoning(
                should_knock=True,
                reasoning="Knocked: GIN!",
                score=1.0,
                factors=factors,
            )

        # Can't knock if deadwood > 10
        if deadwood > 10:
            factors.append("Cannot knock: deadwood > 10")
            return KnockReasoning(
                should_knock=False,
                reasoning=f"No knock: deadwood={deadwood} > 10",
                score=None,
                factors=factors,
            )

        # Use stored context if not provided
        ctx = context or self._current_context

        # Fall back to BasicAI if no context or context-knock disabled
        if ctx is None or not self.context_config.use_context_knock:
            factors.append("Falling back to BasicAI (no context)")
            return super().should_knock_with_reasoning(hand)

        # Edge case 2: Always knock if deck nearly empty (avoid draw)
        if ctx.deck_remaining <= 4:
            factors.append(f"Deck nearly empty: {ctx.deck_remaining} cards")
            return KnockReasoning(
                should_knock=True,
                reasoning=f"Knocked: deck nearly empty ({ctx.deck_remaining} cards remain)",
                score=1.0,
                factors=factors,
            )

        # Edge case 3: Always knock if it would win the game
        potential_points = 25 if deadwood == 0 else 10 - deadwood
        if ctx.my_score + potential_points >= ctx.target_score:
            factors.append("Game-winning knock!")
            return KnockReasoning(
                should_knock=True,
                reasoning="Knocked: game-winning!",
                score=1.0,
                factors=factors,
            )

        # Calculate knock score with detailed factor tracking
        knock_score, score_factors = self._calculate_knock_score_with_factors(hand, ctx)
        factors.extend(score_factors)

        # Make decision
        threshold = self.context_config.knock_decision_threshold
        should_knock = knock_score >= threshold
        factors.append(f"Threshold: {threshold:.2f}")

        if should_knock:
            return KnockReasoning(
                should_knock=True,
                reasoning=f"Knocked with score {knock_score:.2f} (threshold={threshold:.2f})",
                score=knock_score,
                factors=factors,
            )
        else:
            return KnockReasoning(
                should_knock=False,
                reasoning=f"No knock: score {knock_score:.2f} < threshold {threshold:.2f}",
                score=knock_score,
                factors=factors,
            )

    def _calculate_knock_score_with_factors(
        self, hand: Hand, context: GameContext
    ) -> tuple[float, list[str]]:
        """Calculate knock score and return detailed factors.

        Args:
            hand: Current hand.
            context: Game context.

        Returns:
            Tuple of (knock_score, list of factor strings).
        """
        deadwood = hand.deadwood_total
        factors: list[str] = []

        # Base score: (10 - deadwood) / 10
        base_score = (10 - deadwood) / 10.0
        factors.append(f"Base score: {base_score:.2f}")
        score = base_score

        # Gin pursuit modifier
        if deadwood <= self.context_config.gin_pursuit_threshold:
            pursue_gin, gin_prob = self._should_pursue_gin(hand, context)
            if pursue_gin:
                gin_modifier = -self.context_config.gin_pursuit_weight
                score += gin_modifier
                factors.append(f"Gin pursuit: {gin_modifier:+.2f} (prob={gin_prob:.2f})")

        # Undercut risk modifier
        threat_level = self.opponent_model.estimate_threat_level(context)
        if threat_level >= self.context_config.undercut_risk_threshold:
            undercut_modifier = -self.context_config.undercut_risk_weight * threat_level
            score += undercut_modifier
            factors.append(f"Undercut risk: {undercut_modifier:+.2f} (threat={threat_level:.2f})")

        # Deck urgency modifier
        deck_remaining_pct = 1.0 - context.deck_position_pct
        if deck_remaining_pct < self.context_config.late_game_knock_threshold:
            urgency = 1.0 - (deck_remaining_pct / self.context_config.late_game_knock_threshold)
            urgency_modifier = self.context_config.deck_urgency_weight * urgency
            score += urgency_modifier
            factors.append(f"Deck urgency: {urgency_modifier:+.2f} (deck={deck_remaining_pct:.0%})")

        # Score pressure modifier
        points_to_win = context.points_to_win
        opp_points_to_win = context.opponent_points_to_win

        if points_to_win <= 10 - deadwood:
            score += 0.5
            factors.append("Game-winning: +0.50")
        elif opp_points_to_win <= 15:
            score += 0.3
            factors.append("Opponent close: +0.30")
        elif context.score_differential < -self.context_config.knock_trailing_threshold:
            score += 0.2
            factors.append("Trailing: +0.20")
        elif context.score_differential > self.context_config.knock_leading_threshold:
            score -= 0.2
            factors.append("Leading: -0.20")

        # Opponent strength modifier
        estimated_opp_deadwood = self.opponent_model.estimate_deadwood(context)
        if estimated_opp_deadwood >= self.context_config.opponent_high_deadwood_threshold:
            score += 0.3
            factors.append(f"Opponent weak: +0.30 (est={estimated_opp_deadwood})")
        elif estimated_opp_deadwood <= self.context_config.opponent_low_deadwood_threshold:
            score -= 0.2
            factors.append(f"Opponent strong: -0.20 (est={estimated_opp_deadwood})")

        factors.append(f"Final score: {score:.2f}")
        return score, factors


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
