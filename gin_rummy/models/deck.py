"""Deck of cards for Gin Rummy."""

import random

from gin_rummy.models.card import Card, Rank, Suit


class DeckEmptyError(Exception):
    """Raised when attempting to draw from an empty deck."""

    pass


class Deck:
    """A standard 52-card deck with shuffle and draw operations."""

    def __init__(self) -> None:
        """Create a new deck with all 52 cards in order."""
        self._cards: list[Card] = [Card(rank, suit) for suit in Suit for rank in Rank]

    def shuffle(self) -> None:
        """Randomize the order of cards in the deck."""
        random.shuffle(self._cards)

    def draw(self) -> Card:
        """Remove and return the top card from the deck.

        Raises:
            DeckEmptyError: If the deck has no cards remaining.
        """
        if not self._cards:
            raise DeckEmptyError("Cannot draw from an empty deck")
        return self._cards.pop()

    def draw_multiple(self, n: int) -> list[Card]:
        """Draw n cards from the deck.

        Args:
            n: Number of cards to draw.

        Returns:
            List of drawn cards.

        Raises:
            DeckEmptyError: If not enough cards remain.
        """
        if n > len(self._cards):
            raise DeckEmptyError(f"Cannot draw {n} cards, only {len(self._cards)} remaining")
        return [self.draw() for _ in range(n)]

    def __len__(self) -> int:
        """Return the number of cards remaining in the deck."""
        return len(self._cards)

    def __iter__(self):
        """Remaining cards, bottom first (the next draw is the last one)."""
        return iter(self._cards)

    @property
    def is_empty(self) -> bool:
        """Return True if the deck has no cards."""
        return len(self._cards) == 0
