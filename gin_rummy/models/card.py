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

    @property
    def is_red(self) -> bool:
        """Return True if this is a red suit (hearts or diamonds)."""
        return self in (Suit.HEARTS, Suit.DIAMONDS)

    @property
    def code(self) -> str:
        """One-letter ASCII code: C, D, H or S."""
        return self.name[0]


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

    def colored_str(self, red: str = "\033[91m", reset: str = "\033[0m") -> str:
        """Return colored string representation (red for hearts/diamonds)."""
        s = str(self)
        if self.suit.is_red:
            return f"{red}{s}{reset}"
        return s

    def __repr__(self) -> str:
        return f"Card({self.rank.name}, {self.suit.name})"

    def __hash__(self) -> int:
        # Stable across processes: the dataclass default hashes the enum
        # *names*, and str hashes are salted per process (PYTHONHASHSEED), so
        # set iteration order of cards used to differ between runs.
        return self.index

    def __lt__(self, other: "Card") -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        if self.rank != other.rank:
            return self.rank < other.rank
        return list(Suit).index(self.suit) < list(Suit).index(other.suit)

    # ---- ASCII codec: the single serialization used by the DB, the web API,
    # ---- the CLI tools and the tests ("AS", "10H", "KD").

    @property
    def code(self) -> str:
        """ASCII code like 'AS', '10H', 'KD' (rank short name + suit letter)."""
        return f"{self.rank.short_name}{self.suit.code}"

    @classmethod
    def parse(cls, code: str) -> "Card":
        """Parse an ASCII code like 'AS', '10H' or 'KD' into a Card.

        'T' is accepted as an alias for ten on input only. Matching is
        case-sensitive: callers that want to be lenient should upper-case
        first.

        Raises:
            ValueError: If the string is not a valid card code.
        """
        if not isinstance(code, str) or len(code) < 2:
            raise ValueError(f"Invalid card code: {code!r}")
        rank_str, suit_str = code[:-1], code[-1]
        rank = _RANK_BY_CODE.get(rank_str)
        suit = _SUIT_BY_CODE.get(suit_str)
        if rank is None or suit is None:
            raise ValueError(f"Invalid card code: {code!r}")
        return cls(rank, suit)

    # ---- Dense index 0..51 (suit-major: clubs, diamonds, hearts, spades),
    # ---- shared by StatisticalAI's stats file and the learning encoders.

    @property
    def index(self) -> int:
        """Index 0-51: suit position * 13 + (rank value - 1)."""
        return _SUIT_POS[self.suit] * 13 + self.rank.value - 1

    @classmethod
    def from_index(cls, index: int) -> "Card":
        """Inverse of `Card.index`."""
        if not 0 <= index < 52:
            raise ValueError(f"Card index out of range: {index}")
        return cls(Rank(index % 13 + 1), _SUITS_IN_ORDER[index // 13])


_SUITS_IN_ORDER: tuple[Suit, ...] = tuple(Suit)
_SUIT_POS: dict[Suit, int] = {suit: i for i, suit in enumerate(_SUITS_IN_ORDER)}
_SUIT_BY_CODE: dict[str, Suit] = {suit.code: suit for suit in Suit}
_RANK_BY_CODE: dict[str, Rank] = {rank.short_name: rank for rank in Rank}
_RANK_BY_CODE["T"] = Rank.TEN  # input alias only; `code` always emits "10"
