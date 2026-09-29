"""Dynamic draw threshold: how much a draw must improve the hand, given the game state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gin_rummy.models.game_context import GameContext

if TYPE_CHECKING:
    from gin_rummy.config import ContextAwareAIConfig


class DynamicThresholdCalculator:
    """Calculates dynamic min_deadwood_improvement threshold based on game context."""

    def __init__(self, config: ContextAwareAIConfig | None = None) -> None:
        """Initialize with optional config."""
        if config:
            self.base_threshold = config.base_draw_threshold
            self.max_deck_modifier = config.max_deck_modifier
            self.max_outs_modifier = config.max_outs_modifier
            self.trailing_threshold = config.trailing_aggressive_threshold
            self.leading_threshold = config.leading_conservative_threshold
        else:
            self.base_threshold = 1
            self.max_deck_modifier = 2.0
            self.max_outs_modifier = 2.0
            self.trailing_threshold = 50
            self.leading_threshold = 30

    def calculate_threshold(self, context: GameContext) -> int:
        """Calculate the dynamic draw threshold based on game context.

        Returns:
            Minimum deadwood improvement needed to take from discard.
            Lower = more aggressive, Higher = more conservative.
        """
        base = float(self.base_threshold)

        # Deck position: late game = more desperate = lower threshold
        # deck_position_pct: 0 = full, 1 = empty
        deck_modifier = -self.max_deck_modifier * context.deck_position_pct

        # Outs: many live outs = can afford to wait = higher threshold
        outs_modifier = 0.0
        if context.my_outs:
            outs_modifier = min(context.my_outs.live_out_count / 10.0, self.max_outs_modifier)

        # Score pressure
        score_modifier = 0.0
        if context.score_differential < -self.trailing_threshold:
            score_modifier = -2.0  # Very aggressive when trailing badly
        elif context.score_differential < -20:
            score_modifier = -1.0  # Somewhat aggressive
        elif context.score_differential > self.leading_threshold:
            score_modifier = 1.0  # Conservative when leading

        threshold = base + deck_modifier + outs_modifier + score_modifier

        # Clamp to reasonable range
        return max(0, min(5, int(threshold)))
