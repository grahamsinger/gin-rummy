"""AI decision types and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gin_rummy.models import Card


class DrawChoice(Enum):
    """AI's choice of where to draw from."""
    DECK = auto()
    DISCARD = auto()


@dataclass
class AIDecision:
    """Container for AI's turn decisions."""
    draw_from: DrawChoice
    discard: Card
    should_knock: bool


@dataclass
class DrawReasoning:
    """Reasoning for a draw decision."""
    choice: DrawChoice
    reasoning: str  # e.g., "Took Q♠ from discard: reduces deadwood by 8"
    factors: list[str]


@dataclass
class DiscardReasoning:
    """Reasoning for a discard decision."""
    card: Card
    reasoning: str  # e.g., "Discarded 7♥: highest deadwood, no meld potential"
    factors: list[str]
    options_considered: list[tuple[str, int]]  # [(card_str, deadwood), ...]


@dataclass
class KnockReasoning:
    """Reasoning for a knock decision."""
    should_knock: bool
    reasoning: str  # e.g., "Knocked with score 0.65"
    score: float | None  # knock score (for context-aware AI)
    factors: list[str]


@dataclass
class TurnReasoning:
    """Complete reasoning for an AI turn."""
    draw: DrawReasoning
    discard: DiscardReasoning
    knock: KnockReasoning | None = None
