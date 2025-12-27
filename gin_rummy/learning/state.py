"""State encoding for neural network input.

Encodes game state into fixed-size tensors for the DQN networks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import torch

if TYPE_CHECKING:
    from gin_rummy.context import GameContext, KnownCards, OpponentModel
    from gin_rummy.models import Card, Hand, Rank, Suit


# Card encoding: 52 cards indexed as suit * 13 + rank
# Suits: CLUBS=0, DIAMONDS=1, HEARTS=2, SPADES=3
# Ranks: ACE=0, TWO=1, ..., KING=12
SUIT_ORDER = ["CLUBS", "DIAMONDS", "HEARTS", "SPADES"]
NUM_CARDS = 52
NUM_RANKS = 13
NUM_SUITS = 4


def card_to_index(card: Card) -> int:
    """Convert a card to its index (0-51)."""
    suit_idx = SUIT_ORDER.index(card.suit.name)
    rank_idx = card.rank.value - 1  # ACE=1 -> 0, KING=13 -> 12
    return suit_idx * NUM_RANKS + rank_idx


def index_to_card_tuple(idx: int) -> tuple[int, int]:
    """Convert index to (suit_idx, rank_idx) tuple."""
    suit_idx = idx // NUM_RANKS
    rank_idx = idx % NUM_RANKS
    return suit_idx, rank_idx


@dataclass
class StateEncoder:
    """Encodes game state into tensors for neural network input.

    State vector components:
    - Hand (52): One-hot for cards in hand
    - Dead cards (52): Multi-hot for cards known unavailable
    - Discard top (52): One-hot for top of discard pile
    - Opponent pickup ranks (13): Normalized counts
    - Opponent pickup suits (4): Normalized counts
    - Opponent discard ranks (13): Normalized counts
    - Opponent discard suits (4): Normalized counts
    - Game features (8): Normalized scalar features
    - Drawn card (52): One-hot for just-drawn card (discard decision only)

    Total: 52 + 52 + 52 + 13 + 4 + 13 + 4 + 8 = 198 (draw/knock)
           + 52 = 250 (discard)
    """

    # State sizes for each decision type
    DRAW_STATE_SIZE: int = 198
    DISCARD_STATE_SIZE: int = 250
    KNOCK_STATE_SIZE: int = 198

    def encode_hand(self, hand: Hand) -> np.ndarray:
        """Encode hand as 52-dimensional one-hot vector."""
        encoding = np.zeros(NUM_CARDS, dtype=np.float32)
        for card in hand:
            encoding[card_to_index(card)] = 1.0
        return encoding

    def encode_card(self, card: Card | None) -> np.ndarray:
        """Encode a single card as 52-dimensional one-hot vector."""
        encoding = np.zeros(NUM_CARDS, dtype=np.float32)
        if card is not None:
            encoding[card_to_index(card)] = 1.0
        return encoding

    def encode_card_set(self, cards: set[Card] | frozenset[Card]) -> np.ndarray:
        """Encode a set of cards as 52-dimensional multi-hot vector."""
        encoding = np.zeros(NUM_CARDS, dtype=np.float32)
        for card in cards:
            encoding[card_to_index(card)] = 1.0
        return encoding

    def encode_known_cards(self, known: KnownCards) -> np.ndarray:
        """Encode dead/unavailable cards as multi-hot vector."""
        return self.encode_card_set(known.dead_cards)

    def encode_opponent_model(self, model: OpponentModel | None) -> np.ndarray:
        """Encode opponent patterns as normalized counts.

        Returns 34-dimensional vector:
        - 13: Pickup counts by rank (normalized)
        - 4: Pickup counts by suit (normalized)
        - 13: Discard counts by rank (normalized)
        - 4: Discard counts by suit (normalized)
        """
        encoding = np.zeros(34, dtype=np.float32)

        if model is None:
            return encoding

        # Normalize by total observations (avoid division by zero)
        pickup_norm = max(model.total_pickups, 1)
        discard_norm = max(model.total_discards, 1)

        # Pickup patterns by rank (indices 0-12)
        from gin_rummy.models import Rank

        for rank in Rank:
            rank_idx = rank.value - 1
            encoding[rank_idx] = model.picked_up_ranks.get(rank, 0) / pickup_norm

        # Pickup patterns by suit (indices 13-16)
        from gin_rummy.models import Suit

        for i, suit in enumerate(Suit):
            encoding[13 + i] = model.picked_up_suits.get(suit, 0) / pickup_norm

        # Discard patterns by rank (indices 17-29)
        for rank in Rank:
            rank_idx = rank.value - 1
            encoding[17 + rank_idx] = model.discarded_ranks.get(rank, 0) / discard_norm

        # Discard patterns by suit (indices 30-33)
        for i, suit in enumerate(Suit):
            encoding[30 + i] = model.discarded_suits.get(suit, 0) / discard_norm

        return encoding

    def encode_game_features(
        self, hand: Hand, context: GameContext | None
    ) -> np.ndarray:
        """Encode scalar game features as normalized values.

        Returns 8-dimensional vector:
        - deck_position_pct: 0.0 (full) to 1.0 (empty)
        - my_deadwood_normalized: deadwood / 100
        - can_knock: 1.0 if deadwood <= 10, else 0.0
        - is_gin: 1.0 if deadwood == 0, else 0.0
        - score_differential_normalized: (my - opp) / 100, clamped to [-1, 1]
        - points_to_win_normalized: points_to_win / 100
        - meld_count_normalized: num_melds / 4
        - live_outs_normalized: live_outs / 20 (capped at 1.0)
        """
        encoding = np.zeros(8, dtype=np.float32)

        deadwood = hand.deadwood_total

        if context is not None:
            encoding[0] = context.deck_position_pct
            encoding[4] = np.clip(context.score_differential / 100.0, -1.0, 1.0)
            encoding[5] = context.points_to_win / 100.0

            if context.my_outs is not None:
                encoding[7] = min(context.my_outs.live_out_count / 20.0, 1.0)

        encoding[1] = deadwood / 100.0
        encoding[2] = 1.0 if deadwood <= 10 else 0.0
        encoding[3] = 1.0 if deadwood == 0 else 0.0

        # Count melds
        analysis = hand.analyze()
        encoding[6] = len(analysis.melds) / 4.0

        return encoding

    def encode_draw_state(
        self,
        hand: Hand,
        discard_top: Card | None,
        context: GameContext | None,
        opponent_model: OpponentModel | None = None,
    ) -> torch.Tensor:
        """Encode full state for draw decision.

        Returns tensor of shape (DRAW_STATE_SIZE,).
        """
        # Use context's known_cards if available
        known = context.known_cards if context else None

        components = [
            self.encode_hand(hand),  # 52
            self.encode_known_cards(known) if known else np.zeros(52),  # 52
            self.encode_card(discard_top),  # 52
            self.encode_opponent_model(opponent_model),  # 34
            self.encode_game_features(hand, context),  # 8
        ]

        state = np.concatenate(components)
        return torch.from_numpy(state)

    def encode_discard_state(
        self,
        hand: Hand,
        drawn_card: Card,
        context: GameContext | None,
        opponent_model: OpponentModel | None = None,
    ) -> torch.Tensor:
        """Encode full state for discard decision.

        Note: hand should have 11 cards (after drawing).
        Returns tensor of shape (DISCARD_STATE_SIZE,).
        """
        known = context.known_cards if context else None

        components = [
            self.encode_hand(hand),  # 52
            self.encode_known_cards(known) if known else np.zeros(52),  # 52
            np.zeros(52, dtype=np.float32),  # No discard top during discard decision
            self.encode_opponent_model(opponent_model),  # 34
            self.encode_game_features(hand, context),  # 8
            self.encode_card(drawn_card),  # 52 - the card we just drew
        ]

        state = np.concatenate(components)
        return torch.from_numpy(state)

    def encode_knock_state(
        self,
        hand: Hand,
        context: GameContext | None,
        opponent_model: OpponentModel | None = None,
    ) -> torch.Tensor:
        """Encode full state for knock decision.

        Note: hand should have 10 cards (after discarding).
        Returns tensor of shape (KNOCK_STATE_SIZE,).
        """
        known = context.known_cards if context else None

        components = [
            self.encode_hand(hand),  # 52
            self.encode_known_cards(known) if known else np.zeros(52),  # 52
            np.zeros(52, dtype=np.float32),  # No discard top for knock decision
            self.encode_opponent_model(opponent_model),  # 34
            self.encode_game_features(hand, context),  # 8
        ]

        state = np.concatenate(components)
        return torch.from_numpy(state)

    def get_card_indices(self, hand: Hand) -> list[int]:
        """Get the card indices for each card in hand (for discard action mapping)."""
        return [card_to_index(card) for card in hand]
