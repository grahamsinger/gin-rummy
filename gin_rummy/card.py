"""Card, Suit, and Rank definitions for Gin Rummy."""

from dataclasses import dataclass
from enum import Enum
from functools import total_ordering


class Suit(Enum):
    """Card suits with display symbols."""

    CLUBS = "clubs"
    DIAMONDS = "diamonds"
    HEARTS = "hearts"
    SPADES = "spades"

    @property
    def symbol(self) -> str:
        """Return the Unicode symbol for the suit."""
        symbols = {
            Suit.CLUBS: "♣",
            Suit.DIAMONDS: "♦",
            Suit.HEARTS: "♥",
            Suit.SPADES: "♠",
        }
        return symbols[self]


@total_ordering
class Rank(Enum):
    """Card ranks with values 1-13."""

    ACE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13

    @property
    def deadwood_value(self) -> int:
        """Return the deadwood value: Ace=1, Face cards=10, others=face value."""
        if self.value >= 10:
            return 10
        return self.value

    @property
    def short_name(self) -> str:
        """Return short display name (A, 2-10, J, Q, K)."""
        names = {
            Rank.ACE: "A",
            Rank.JACK: "J",
            Rank.QUEEN: "Q",
            Rank.KING: "K",
        }
        return names.get(self, str(self.value))

    def __lt__(self, other: "Rank") -> bool:
        if not isinstance(other, Rank):
            return NotImplemented
        return self.value < other.value


@total_ordering
@dataclass(frozen=True)
class Card:
    """An immutable playing card with suit and rank."""

    rank: Rank
    suit: Suit

    @property
    def deadwood_value(self) -> int:
        """Return the deadwood value of this card."""
        return self.rank.deadwood_value

    def __str__(self) -> str:
        """Return string representation like 'A♠', '10♥', 'K♣'."""
        return f"{self.rank.short_name}{self.suit.symbol}"

    def __repr__(self) -> str:
        return f"Card({self.rank.name}, {self.suit.name})"

    def __lt__(self, other: "Card") -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        if self.rank != other.rank:
            return self.rank < other.rank
        return list(Suit).index(self.suit) < list(Suit).index(other.suit)
