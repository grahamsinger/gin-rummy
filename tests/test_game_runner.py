"""Tests for the shared AI turn runner."""

from __future__ import annotations

from gin_rummy.ai import BasicAI
from gin_rummy.game_runner import record_opponent_discard, record_opponent_pickup
from gin_rummy.models import Card, Rank, Suit


class TrackingAI(BasicAI):
    """An AI that tracks opponent actions but is not a ContextAwareAI."""

    def __init__(self) -> None:
        super().__init__()
        self.pickups: list[Card] = []
        self.discards: list[Card] = []

    def record_opponent_pickup(self, card: Card) -> None:
        self.pickups.append(card)

    def record_opponent_discard(self, card: Card) -> None:
        self.discards.append(card)


class TestOpponentTrackingForwarding:
    """B4: forwarding must be by capability, not by concrete class."""

    def test_forwards_to_any_ai_with_the_methods(self):
        ai = TrackingAI()
        card = Card(Rank.SEVEN, Suit.HEARTS)
        record_opponent_pickup(ai, card)
        record_opponent_discard(ai, card)
        assert ai.pickups == [card]
        assert ai.discards == [card]

    def test_noop_for_plain_basic_ai_and_none(self):
        card = Card(Rank.SEVEN, Suit.HEARTS)
        record_opponent_pickup(BasicAI(), card)
        record_opponent_discard(BasicAI(), card)
        record_opponent_pickup(None, card)
        record_opponent_discard(None, card)
