"""Outs: the cards that would improve a hand, and the analysis that lists them."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from gin_rummy.models import Card

if TYPE_CHECKING:
    pass


class OutType(Enum):
    """Type of 'out' - how a card would help the hand."""

    MELD_COMPLETING = auto()  # Completes a 3+ card meld
    RUN_EXTENDING = auto()  # Extends an existing run by 1
    SET_BUILDING = auto()  # Creates a pair or adds to a pair


@dataclass
class OutInfo:
    """Information about a single 'out' card."""

    card: Card
    out_type: OutType
    weight: float  # Weighted value (higher = more valuable)
    description: str  # e.g., "completes 7-8-9 hearts run"
    is_dead: bool = False  # True if card is known to be unavailable


@dataclass
class OutsAnalysis:
    """Complete outs analysis for a hand."""

    meld_completing_outs: list[OutInfo] = field(default_factory=list)
    partial_outs: list[OutInfo] = field(default_factory=list)

    @property
    def all_outs(self) -> list[OutInfo]:
        """All outs combined."""
        return self.meld_completing_outs + self.partial_outs

    @property
    def live_out_count(self) -> int:
        """Count of outs that are not dead."""
        return sum(1 for o in self.all_outs if not o.is_dead)

    @property
    def dead_out_count(self) -> int:
        """Count of outs that are known dead."""
        return sum(1 for o in self.all_outs if o.is_dead)

    @property
    def weighted_value(self) -> float:
        """Sum of weighted values of all live outs."""
        return sum(o.weight for o in self.all_outs if not o.is_dead)

    @property
    def live_meld_completing_cards(self) -> set[Card]:
        """Set of live meld-completing out cards."""
        return {o.card for o in self.meld_completing_outs if not o.is_dead}
