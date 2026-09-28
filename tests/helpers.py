"""Shared helpers for tests (plain functions; fixtures live in conftest.py)."""

from __future__ import annotations

from gin_rummy.config import AIConfig, Config, MonteCarloAIConfig
from gin_rummy.context import GameContext, KnownCards
from gin_rummy.models import Card, Hand, Rank, Suit

_RANKS = {
    "A": Rank.ACE, "2": Rank.TWO, "3": Rank.THREE, "4": Rank.FOUR, "5": Rank.FIVE,
    "6": Rank.SIX, "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE, "10": Rank.TEN,
    "J": Rank.JACK, "Q": Rank.QUEEN, "K": Rank.KING,
}
_SUITS = {"S": Suit.SPADES, "H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS}


def card(code: str) -> Card:
    """Build a Card from a code like "7S" or "10H"."""
    return Card(_RANKS[code[:-1]], _SUITS[code[-1]])


def cards(codes: str) -> list[Card]:
    """Build a list of Cards from a space-separated string like "7S 8S 9S KC"."""
    return [card(c) for c in codes.split()]


def hand(codes: str) -> Hand:
    """Build a Hand from a space-separated string of card codes."""
    return Hand(cards(codes))


def make_ai_config(knock_strategy: str = "always") -> Config:
    """Config for BasicAI/ContextAwareAI tests with a chosen knock strategy."""
    config = Config()
    config.ai = AIConfig(
        knock_strategy=knock_strategy,
        conservative_knock_threshold=5,
        min_deadwood_improvement=1,
    )
    return config


def make_mc_config(**overrides) -> Config:
    """Fast, sequential MonteCarloAI config for tests."""
    params = dict(
        draw_simulations=10,
        discard_simulations=10,
        knock_simulations=10,
        max_rollout_turns=4,
        min_unknown_for_simulation=3,
        rollout_knock_strategy="conservative",
        rollout_conservative_threshold=3,
        draw_min_advantage=1.5,
        discard_min_advantage=1.0,
        knock_min_advantage=2.0,
        max_workers=1,
        sample_strategy="paired",
        weighted_sampling=True,
        defensive_rollout=True,
        joint_turn_evaluation=True,
    )
    params.update(overrides)
    config = Config()
    config.monte_carlo_ai = MonteCarloAIConfig(**params)
    return config


def make_context(
    hand: Hand,
    deck_remaining: int = 20,
    my_score: int = 0,
    opponent_score: int = 0,
    target_score: int = 100,
) -> GameContext:
    """A GameContext where only my own hand is known."""
    known_cards = KnownCards(
        my_hand=frozenset(hand),
        opponent_hand_known=frozenset(),
        discard_top=None,
        discard_buried=frozenset(),
    )
    return GameContext(
        deck_remaining=deck_remaining,
        deck_position_pct=1.0 - (deck_remaining / 31.0),
        my_score=my_score,
        opponent_score=opponent_score,
        target_score=target_score,
        known_cards=known_cards,
    )
