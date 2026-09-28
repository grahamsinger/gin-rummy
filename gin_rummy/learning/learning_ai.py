"""LearningAI - Reinforcement learning based AI for Gin Rummy.

Uses Deep Q-Networks to make decisions based on learned policies.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

import torch

from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.config import Config
from gin_rummy.context import OpponentModel
from gin_rummy.learning.models import (
    DiscardNet,
    DrawNet,
    KnockNet,
    ModelPersistence,
)
from gin_rummy.learning.state import StateEncoder, card_to_index

if TYPE_CHECKING:
    from gin_rummy.context import GameContext
    from gin_rummy.models import Card, Hand


logger = logging.getLogger(__name__)


class LearningAI(BasicAI):
    """AI that uses trained neural networks for decisions.

    Can operate in two modes:
    - Inference mode (exploration_rate=0): Uses learned policy
    - Training mode (exploration_rate>0): Mixes exploration with exploitation

    The AI uses three separate networks:
    - DrawNet: Decides whether to draw from deck or discard pile
    - DiscardNet: Decides which card to discard
    - KnockNet: Decides whether to knock
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        config: Config | None = None,
        exploration_rate: float = 0.0,
        device: torch.device | str | None = None,
    ) -> None:
        """Initialize LearningAI.

        Args:
            model_path: Path to trained model checkpoint. If None, uses random networks.
            config: Config override for fallback behavior.
            exploration_rate: Probability of random action (0.0 for inference, >0 for training).
            device: Device to run inference on ('cpu', 'cuda', or torch.device).
        """
        super().__init__(config)

        # Set device
        if device is None:
            self.device = torch.device("cpu")
        elif isinstance(device, str):
            self.device = torch.device(device)
        else:
            self.device = device

        self.exploration_rate = exploration_rate
        self.encoder = StateEncoder()

        # Load or initialize networks
        if model_path is not None:
            path = Path(model_path) if isinstance(model_path, str) else model_path
            if ModelPersistence.exists(path):
                logger.info("Loading model from %s", path)
                self.draw_net, self.discard_net, self.knock_net, self.metadata = ModelPersistence.load(
                    path, self.device
                )
            else:
                logger.warning("Model path %s not found, using random networks", path)
                self._init_random_networks()
        else:
            self._init_random_networks()

        # Move networks to device
        self.draw_net = self.draw_net.to(self.device)
        self.discard_net = self.discard_net.to(self.device)
        self.knock_net = self.knock_net.to(self.device)

        # Context tracking (like ContextAwareAI)
        self._current_context: GameContext | None = None
        self.opponent_model = OpponentModel()

        # Track drawn card for discard decision
        self._drawn_card: Card | None = None

    def _init_random_networks(self) -> None:
        """Initialize networks with random weights."""
        self.draw_net = DrawNet()
        self.discard_net = DiscardNet()
        self.knock_net = KnockNet()
        self.metadata: dict = {}

    def update_context(self, context: GameContext) -> None:
        """Update the current game context.

        Args:
            context: Current game state snapshot.
        """
        self._current_context = context

    def record_opponent_discard(self, card: Card) -> None:
        """Record that opponent discarded a card.

        Args:
            card: The card opponent discarded.
        """
        self.opponent_model.record_discard(card)

    def record_opponent_pickup(self, card: Card) -> None:
        """Record that opponent picked up from discard.

        Args:
            card: The card opponent picked up.
        """
        self.opponent_model.record_pickup(card)

    def reset_for_new_hand(self) -> None:
        """Reset tracking for a new hand."""
        self.opponent_model.reset()
        self._current_context = None
        self._drawn_card = None

    def decide_draw(
        self,
        hand: Hand,
        discard_top: Card | None,
        context: GameContext | None = None,
    ) -> DrawChoice:
        """Use DrawNet to decide where to draw from.

        Args:
            hand: Current hand.
            discard_top: Top card of discard pile, or None if empty.
            context: Optional game context.

        Returns:
            DrawChoice indicating where to draw from.
        """
        # Use provided context or fall back to stored context
        ctx = context or self._current_context

        # Must draw from deck if discard is empty
        if discard_top is None:
            logger.info("Draw decision: DECK (discard pile empty)")
            return DrawChoice.DECK

        # Exploration: random action
        if self.exploration_rate > 0 and random.random() < self.exploration_rate:
            choice = random.choice([DrawChoice.DECK, DrawChoice.DISCARD])
            logger.debug("Draw decision: %s (exploration)", choice.name)
            return choice

        # Encode state and get Q-values
        state = self.encoder.encode_draw_state(hand, discard_top, ctx, self.opponent_model)
        state = state.unsqueeze(0).to(self.device).float()  # Add batch dimension, ensure float32

        with torch.no_grad():
            q_values = self.draw_net(state)

        # Select action with highest Q-value
        # Index 0 = DECK, Index 1 = DISCARD
        action = q_values.argmax(dim=1).item()
        choice = DrawChoice.DISCARD if action == 1 else DrawChoice.DECK

        logger.info(
            "Draw decision: %s (Q-values: deck=%.3f, discard=%.3f)",
            choice.name,
            q_values[0, 0].item(),
            q_values[0, 1].item(),
        )

        return choice

    def decide_discard(self, hand: Hand) -> Card:
        """Use DiscardNet to decide which card to discard.

        Args:
            hand: Current hand (should have 11 cards after drawing).

        Returns:
            Card to discard.
        """
        cards = list(hand)

        # Exploration: random action
        if self.exploration_rate > 0 and random.random() < self.exploration_rate:
            choice = random.choice(cards)
            logger.debug("Discard decision: %s (exploration)", choice)
            return choice

        # Note: _drawn_card should be set by make_turn_decision before this is called
        drawn_card = self._drawn_card
        if drawn_card is None:
            # This happens for the initial discard (before first draw)
            # Fall back to BasicAI logic for this case
            logger.debug("Initial discard - using BasicAI fallback")
            return super().decide_discard(hand)

        # Encode state
        state = self.encoder.encode_discard_state(hand, drawn_card, self._current_context, self.opponent_model)
        state = state.unsqueeze(0).to(self.device).float()

        with torch.no_grad():
            q_values = self.discard_net(state)  # Shape: (1, 52)

        # Get card indices for cards in hand
        card_indices = [card_to_index(c) for c in cards]

        # Mask: set non-hand cards to -inf so they won't be selected
        mask = torch.full((52,), float("-inf"), device=self.device)
        for idx in card_indices:
            mask[idx] = 0.0

        masked_q = q_values[0] + mask
        best_card_idx = masked_q.argmax().item()

        # Find the card with this index
        choice = None
        for card in cards:
            if card_to_index(card) == best_card_idx:
                choice = card
                break

        if choice is None:
            # Fallback (shouldn't happen)
            choice = cards[0]

        logger.info(
            "Discard decision: %s (Q-value=%.3f, best of %d cards)",
            choice,
            masked_q[best_card_idx].item(),
            len(cards),
        )

        return choice

    def should_knock(self, hand: Hand) -> bool:
        """Use KnockNet to decide whether to knock.

        Args:
            hand: Current hand (should have 10 cards).

        Returns:
            True if AI should knock.
        """
        deadwood = hand.deadwood_total

        # Can't knock if deadwood over threshold
        if deadwood > self.knock_threshold:
            logger.debug("Knock decision: NO (deadwood=%d > %d)", deadwood, self.knock_threshold)
            return False

        # Always knock on gin
        if deadwood == 0:
            logger.info("Knock decision: YES - GIN!")
            return True

        # Exploration: random action
        if self.exploration_rate > 0 and random.random() < self.exploration_rate:
            choice = random.choice([True, False])
            logger.debug("Knock decision: %s (exploration)", "YES" if choice else "NO")
            return choice

        # Encode state
        state = self.encoder.encode_knock_state(hand, self._current_context, self.opponent_model)
        state = state.unsqueeze(0).to(self.device).float()

        with torch.no_grad():
            q_values = self.knock_net(state)

        # Index 0 = don't knock, Index 1 = knock
        action = q_values.argmax(dim=1).item()
        choice = action == 1

        logger.info(
            "Knock decision: %s (Q-values: no=%.3f, yes=%.3f, deadwood=%d)",
            "YES" if choice else "NO",
            q_values[0, 0].item(),
            q_values[0, 1].item(),
            deadwood,
        )

        return choice

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
        logger.debug("--- LearningAI Turn Start ---")
        logger.debug("Drew: %s", drawn_card)

        # Store drawn card for discard decision
        self._drawn_card = drawn_card

        # Get discard decision
        discard = self.decide_discard(hand)

        # Check if we can knock after discarding
        from gin_rummy.models import Hand as HandClass, analyze_hand

        test_cards = [c for c in hand if c != discard]
        test_analysis = analyze_hand(test_cards)
        can_knock = test_analysis.deadwood_value <= self.knock_threshold

        # Get knock decision
        should_knock = can_knock and self.should_knock(HandClass(test_cards))

        logger.debug(
            "--- LearningAI Turn End --- (discard=%s, knock=%s)",
            discard,
            should_knock,
        )

        return discard, should_knock

    def set_exploration_rate(self, rate: float) -> None:
        """Set the exploration rate.

        Args:
            rate: New exploration rate (0.0 to 1.0).
        """
        self.exploration_rate = max(0.0, min(1.0, rate))

    def get_networks(self) -> tuple[DrawNet, DiscardNet, KnockNet]:
        """Get the neural networks for training.

        Returns:
            Tuple of (draw_net, discard_net, knock_net).
        """
        return self.draw_net, self.discard_net, self.knock_net

    def save(self, path: Path | str, metadata: dict | None = None) -> None:
        """Save the model to a checkpoint file.

        Args:
            path: Path to save the checkpoint.
            metadata: Optional metadata to include.
        """
        save_path = Path(path) if isinstance(path, str) else path
        ModelPersistence.save(
            save_path,
            self.draw_net,
            self.discard_net,
            self.knock_net,
            metadata or self.metadata,
        )
        logger.info("Model saved to %s", save_path)

    def train_mode(self) -> None:
        """Set networks to training mode."""
        self.draw_net.train()
        self.discard_net.train()
        self.knock_net.train()

    def eval_mode(self) -> None:
        """Set networks to evaluation mode."""
        self.draw_net.eval()
        self.discard_net.eval()
        self.knock_net.eval()
