"""Reward calculation for reinforcement learning training.

Provides reward shaping for gin rummy outcomes and intermediate states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gin_rummy.game import RoundResult


@dataclass
class RewardConfig:
    """Configuration for reward shaping.

    Attributes:
        win_by_gin: Reward for winning with gin (0 deadwood)
        win_by_knock: Base reward for winning by knocking
        win_by_undercut: Reward for winning by undercut (defender beats knocker)
        loss_multiplier: Multiplier for points lost (negative reward)
        points_multiplier: Multiplier for points won/lost
        deadwood_reduction_bonus: Reward per point of deadwood reduced
        meld_completion_bonus: Reward for completing a meld
        key_out_pickup_bonus: Reward for picking up a meld-completing card
        undercut_penalty: Penalty for being undercut (knocked and lost)
        draw_round_reward: Reward when round ends in a draw
    """

    win_by_gin: float = 50.0
    win_by_knock: float = 20.0
    win_by_undercut: float = 30.0
    loss_multiplier: float = -1.0
    points_multiplier: float = 0.2
    deadwood_reduction_bonus: float = 0.1
    meld_completion_bonus: float = 1.0
    key_out_pickup_bonus: float = 0.5
    undercut_penalty: float = -5.0
    draw_round_reward: float = 0.0
    # Draw-specific rewards
    discard_kept_bonus: float = 0.5  # Bonus for keeping a card from discard pile
    discard_wasted_penalty: float = -1.0  # Penalty for taking from discard then discarding it


class RewardCalculator:
    """Calculates rewards for training the LearningAI.

    Provides both end-of-round rewards and intermediate (per-turn) rewards
    to shape learning effectively.
    """

    def __init__(self, config: RewardConfig | None = None) -> None:
        """Initialize reward calculator.

        Args:
            config: Reward configuration. Uses defaults if None.
        """
        self.config = config or RewardConfig()

    def round_end_reward(
        self,
        result: RoundResult,
        player_name: str,
    ) -> float:
        """Calculate reward at end of round.

        Args:
            result: The round result containing winner, points, and method.
            player_name: Name of the player to calculate reward for.

        Returns:
            Reward value (positive for wins, negative for losses).
        """
        if result.winner is None:
            # Draw - no winner
            return self.config.draw_round_reward

        # Check if this player won by comparing with winner's name
        is_winner = result.winner.name == player_name
        points = result.points

        if is_winner:
            # Calculate base reward based on how we won
            if result.is_gin:
                base_reward = self.config.win_by_gin
            elif result.is_undercut:
                # We won by undercut (opponent knocked, we had lower deadwood)
                base_reward = self.config.win_by_undercut
            else:
                # Regular knock win
                base_reward = self.config.win_by_knock

            # Add points bonus
            return base_reward + (points * self.config.points_multiplier)

        else:
            # We lost
            base_penalty = 0.0

            # If undercut happened and we lost, we were the knocker who got undercut
            if result.is_undercut:
                # We knocked but got undercut - extra penalty for bad decision
                base_penalty = self.config.undercut_penalty

            # Negative reward based on points lost
            return base_penalty + (points * self.config.loss_multiplier * self.config.points_multiplier)

    def turn_reward(
        self,
        deadwood_before: int,
        deadwood_after: int,
        melds_before: int,
        melds_after: int,
        picked_key_out: bool = False,
    ) -> float:
        """Calculate intermediate reward for a single turn.

        Provides reward shaping to encourage good play patterns
        without waiting for end-of-round feedback.

        Args:
            deadwood_before: Deadwood value before the turn.
            deadwood_after: Deadwood value after the turn.
            melds_before: Number of melds before the turn.
            melds_after: Number of melds after the turn.
            picked_key_out: Whether a meld-completing card was picked up.

        Returns:
            Intermediate reward value.
        """
        reward = 0.0

        # Reward for reducing deadwood
        deadwood_reduction = deadwood_before - deadwood_after
        if deadwood_reduction > 0:
            reward += deadwood_reduction * self.config.deadwood_reduction_bonus

        # Reward for completing melds
        new_melds = melds_after - melds_before
        if new_melds > 0:
            reward += new_melds * self.config.meld_completion_bonus

        # Reward for picking up key outs
        if picked_key_out:
            reward += self.config.key_out_pickup_bonus

        return reward

    def draw_reward(
        self,
        drew_from_discard: bool,
        drawn_card: object,
        discarded_card: object,
        deadwood_before: int,
        deadwood_after: int,
    ) -> float:
        """Calculate reward specific to the draw decision.

        This provides targeted feedback for whether drawing from discard
        was a good idea, independent of the overall turn outcome.

        Args:
            drew_from_discard: Whether draw was from discard pile.
            drawn_card: The card that was drawn.
            discarded_card: The card that was discarded after.
            deadwood_before: Deadwood before the turn.
            deadwood_after: Deadwood after the turn.

        Returns:
            Draw-specific reward component.
        """
        if not drew_from_discard:
            # Drawing from deck is neutral (random outcome)
            return 0.0

        # Drew from discard - check if it was a good decision
        if drawn_card == discarded_card:
            # Took from discard and immediately discarded it
            # Bad: revealed interest in that area to opponent for nothing
            return self.config.discard_wasted_penalty

        # Kept the card - but did it actually help?
        deadwood_improvement = deadwood_before - deadwood_after
        if deadwood_improvement > 0:
            # Card actually helped reduce deadwood
            return self.config.discard_kept_bonus
        else:
            # Kept the card but it didn't help - slight penalty
            # (not as bad as wasting, but not good either)
            return self.config.discard_wasted_penalty * 0.3

    def normalize_reward(self, reward: float, scale: float = 100.0) -> float:
        """Normalize reward to a reasonable range.

        Args:
            reward: Raw reward value.
            scale: Scale factor (rewards divided by this).

        Returns:
            Normalized reward.
        """
        return reward / scale
