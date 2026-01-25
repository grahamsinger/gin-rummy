"""Context-aware AI opponent for Gin Rummy."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gin_rummy.models import Card, Hand, analyze_hand
from gin_rummy.config import get_config, Config
from gin_rummy.context import (
    OutsCalculator,
    OpponentModel,
    DynamicThresholdCalculator,
)
from gin_rummy.ai.types import (
    DrawChoice,
    DrawReasoning,
    DiscardReasoning,
    KnockReasoning,
)
from gin_rummy.ai.basic import BasicAI

if TYPE_CHECKING:
    from gin_rummy.context import GameContext


logger = logging.getLogger(__name__)


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
