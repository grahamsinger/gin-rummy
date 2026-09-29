"""JSON shapes the web UI receives: cards, and the round-result data."""

from __future__ import annotations

from dataclasses import dataclass

from gin_rummy.models import Card


def card_to_dict(card: Card) -> dict[str, str]:
    """Convert a Card to a JSON-serializable dict ({"id": "7H", "rank": "7", "suit": "hearts"})."""
    return {"id": card.code, "rank": card.rank.short_name, "suit": card.suit.value}


@dataclass
class HandResultData:
    """Hand data for round result display."""

    cards: list[dict]
    melds: list[dict]
    deadwood: int
    deadwood_cards: list[str]


@dataclass
class RoundResultData:
    """Round result data for JSON serialization."""

    winner: str | None
    points: int
    is_gin: bool
    is_undercut: bool
    is_draw: bool
    player_hand: HandResultData
    opponent_hand: HandResultData
    layoff_cards: list[str] | None = None  # Cards laid off (formatted as strings)
    defender_deadwood_before: int = 0  # Defender's deadwood before layoff
