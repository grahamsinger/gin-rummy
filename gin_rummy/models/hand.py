"""Hand management for Gin Rummy."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from gin_rummy.models.card import Card

if TYPE_CHECKING:
    from gin_rummy.models.melds import HandAnalysis


class CardNotInHandError(Exception):
    """Raised when attempting to remove a card not in the hand."""

    pass


class Hand:
    """A player's hand of cards."""

    def __init__(self, cards: list[Card] | None = None) -> None:
        """Create a hand, optionally with initial cards.

        Args:
            cards: Initial cards to add to hand. Defaults to empty.
        """
        self._cards: list[Card] = list(cards) if cards else []
        self._analysis_cache: HandAnalysis | None = None

    def _invalidate_cache(self) -> None:
        """Invalidate the meld analysis cache."""
        self._analysis_cache = None

    def add(self, card: Card) -> None:
        """Add a card to the hand."""
        self._cards.append(card)
        self._invalidate_cache()

    def remove(self, card: Card) -> None:
        """Remove a specific card from the hand.

        Raises:
            CardNotInHandError: If the card is not in the hand.
        """
        if card not in self._cards:
            raise CardNotInHandError(f"{card} is not in hand")
        self._cards.remove(card)
        self._invalidate_cache()

    def sort(self) -> None:
        """Sort the cards by rank then suit."""
        self._cards.sort()

    @property
    def cards(self) -> list[Card]:
        """Return a copy of the cards list."""
        return list(self._cards)

    def analyze(self) -> HandAnalysis:
        """Analyze the hand to find optimal melds and deadwood.

        Returns:
            HandAnalysis with melds, deadwood cards, and deadwood value.
        """
        from gin_rummy.models.melds import analyze_hand

        if self._analysis_cache is None:
            self._analysis_cache = analyze_hand(self._cards)
        return self._analysis_cache

    @property
    def deadwood_total(self) -> int:
        """Return the optimal deadwood value (accounting for melds)."""
        return self.analyze().deadwood_value

    def __len__(self) -> int:
        """Return the number of cards in the hand."""
        return len(self._cards)

    def __iter__(self) -> Iterator[Card]:
        """Iterate over cards in the hand."""
        return iter(self._cards)

    def __contains__(self, card: Card) -> bool:
        """Check if a card is in the hand."""
        return card in self._cards

    def __getitem__(self, index: int) -> Card:
        """Get card at index."""
        return self._cards[index]

    def __str__(self) -> str:
        """Return string representation of the hand."""
        if not self._cards:
            return "Empty hand"
        return " ".join(str(card) for card in self._cards)

    def __repr__(self) -> str:
        return f"Hand({self._cards!r})"
