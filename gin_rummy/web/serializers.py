"""JSON shapes the web UI receives: cards, and the round-result data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gin_rummy.models import Card
from gin_rummy.models.melds import HandAnalysis


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


def melds_to_dicts(analysis: HandAnalysis) -> list[dict[str, Any]]:
    """[{"type": "set" | "run", "cards": [codes]}] for a hand analysis."""
    return [
        {"type": "set" if meld.meld_type.name == "SET" else "run", "cards": [c.code for c in meld.cards]}
        for meld in analysis.melds
    ]


def hand_result_to_dict(hd: HandResultData) -> dict[str, Any]:
    return {"cards": hd.cards, "melds": hd.melds, "deadwood": hd.deadwood, "deadwood_cards": hd.deadwood_cards}


def round_result_to_dict(rr: RoundResultData) -> dict[str, Any]:
    return {
        "winner": rr.winner,
        "points": rr.points,
        "is_gin": rr.is_gin,
        "is_undercut": rr.is_undercut,
        "is_draw": rr.is_draw,
        "player_hand": hand_result_to_dict(rr.player_hand),
        "opponent_hand": hand_result_to_dict(rr.opponent_hand),
        "layoff_cards": rr.layoff_cards,
        "defender_deadwood_before": rr.defender_deadwood_before,
    }
