"""Tests for the shared AI turn runner."""

from __future__ import annotations

from gin_rummy.ai import BasicAI
from gin_rummy.models import Card, Rank, Suit
from gin_rummy.round_runner import AISeat


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

    def test_seat_forwards_to_any_ai_with_the_methods(self):
        ai = TrackingAI()
        seat = AISeat(ai)
        card = Card(Rank.SEVEN, Suit.HEARTS)
        seat.observe_pickup(card)
        seat.observe_discard(card)
        assert ai.pickups == [card]
        assert ai.discards == [card]

    def test_plain_basic_ai_accepts_the_calls(self):
        seat = AISeat(BasicAI())
        card = Card(Rank.SEVEN, Suit.HEARTS)
        seat.observe_pickup(card)
        seat.observe_discard(card)
        assert seat.ai.opponent_model.total_discards == 1
