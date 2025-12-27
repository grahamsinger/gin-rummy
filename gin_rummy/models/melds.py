"""Meld detection and optimal deadwood calculation for Gin Rummy."""

from dataclasses import dataclass
from enum import Enum, auto
from itertools import combinations

from gin_rummy.models.card import Card, Suit, Rank


class MeldType(Enum):
    """Type of meld."""
    SET = auto()   # 3-4 cards of same rank
    RUN = auto()   # 3+ consecutive cards of same suit


@dataclass(frozen=True)
class Meld:
    """A valid meld (set or run)."""
    cards: tuple[Card, ...]
    meld_type: MeldType

    @property
    def size(self) -> int:
        return len(self.cards)

    def __str__(self) -> str:
        cards_str = " ".join(str(c) for c in self.cards)
        type_str = "Set" if self.meld_type == MeldType.SET else "Run"
        return f"{type_str}: {cards_str}"


def find_all_sets(cards: list[Card]) -> list[Meld]:
    """Find all possible sets (3-4 cards of same rank) in the cards.

    Args:
        cards: List of cards to search.

    Returns:
        List of all valid set melds.
    """
    melds = []

    # Group cards by rank
    by_rank: dict[Rank, list[Card]] = {}
    for card in cards:
        by_rank.setdefault(card.rank, []).append(card)

    # Find sets of 3 or 4
    for rank, rank_cards in by_rank.items():
        if len(rank_cards) >= 3:
            # Add all combinations of 3
            for combo in combinations(rank_cards, 3):
                melds.append(Meld(tuple(sorted(combo)), MeldType.SET))
            # Add set of 4 if available
            if len(rank_cards) == 4:
                melds.append(Meld(tuple(sorted(rank_cards)), MeldType.SET))

    return melds


def find_all_runs(cards: list[Card]) -> list[Meld]:
    """Find all possible runs (3+ consecutive cards of same suit) in the cards.

    Args:
        cards: List of cards to search.

    Returns:
        List of all valid run melds.
    """
    melds = []

    # Group cards by suit
    by_suit: dict[Suit, list[Card]] = {}
    for card in cards:
        by_suit.setdefault(card.suit, []).append(card)

    # Find runs in each suit
    for suit, suit_cards in by_suit.items():
        if len(suit_cards) < 3:
            continue

        # Sort by rank value
        sorted_cards = sorted(suit_cards, key=lambda c: c.rank.value)

        # Find all consecutive sequences of 3+
        # Use dynamic programming approach: for each starting position,
        # find all valid runs starting there
        n = len(sorted_cards)
        for start in range(n):
            run = [sorted_cards[start]]
            for i in range(start + 1, n):
                # Check if consecutive (value differs by 1)
                if sorted_cards[i].rank.value == run[-1].rank.value + 1:
                    run.append(sorted_cards[i])
                    if len(run) >= 3:
                        melds.append(Meld(tuple(run), MeldType.RUN))
                else:
                    break

    return melds


def find_all_melds(cards: list[Card]) -> list[Meld]:
    """Find all possible melds (sets and runs) in the cards.

    Args:
        cards: List of cards to search.

    Returns:
        List of all valid melds.
    """
    return find_all_sets(cards) + find_all_runs(cards)


def _melds_overlap(meld1: Meld, meld2: Meld) -> bool:
    """Check if two melds share any cards."""
    cards1 = set(meld1.cards)
    cards2 = set(meld2.cards)
    return bool(cards1 & cards2)


def _calculate_deadwood(cards: list[Card], used_cards: set[Card]) -> int:
    """Calculate deadwood for cards not in used_cards."""
    return sum(c.deadwood_value for c in cards if c not in used_cards)


def find_optimal_melds(cards: list[Card]) -> tuple[list[Meld], int]:
    """Find the combination of melds that minimizes deadwood.

    This uses a recursive approach with memoization to find the optimal
    non-overlapping set of melds.

    Args:
        cards: List of cards in hand.

    Returns:
        Tuple of (list of optimal melds, deadwood value).
    """
    if not cards:
        return [], 0

    all_melds = find_all_melds(cards)

    if not all_melds:
        # No melds possible, all cards are deadwood
        return [], sum(c.deadwood_value for c in cards)

    # Try all combinations of non-overlapping melds
    best_melds: list[Meld] = []
    best_deadwood = sum(c.deadwood_value for c in cards)

    def find_best(index: int, current_melds: list[Meld], used: set[Card]) -> None:
        nonlocal best_melds, best_deadwood

        deadwood = _calculate_deadwood(cards, used)
        if deadwood < best_deadwood:
            best_deadwood = deadwood
            best_melds = list(current_melds)

        # Pruning: if current deadwood is already 0, we can't do better
        if deadwood == 0:
            return

        # Try adding more melds
        for i in range(index, len(all_melds)):
            meld = all_melds[i]
            meld_cards = set(meld.cards)

            # Skip if overlaps with already used cards
            if meld_cards & used:
                continue

            # Add this meld and recurse
            current_melds.append(meld)
            find_best(i + 1, current_melds, used | meld_cards)
            current_melds.pop()

    find_best(0, [], set())
    return best_melds, best_deadwood


@dataclass
class HandAnalysis:
    """Complete analysis of a hand's melds and deadwood."""
    melds: list[Meld]
    deadwood_cards: list[Card]
    deadwood_value: int

    def __str__(self) -> str:
        lines = []
        if self.melds:
            lines.append("Melds:")
            for meld in self.melds:
                lines.append(f"  {meld}")
        if self.deadwood_cards:
            cards_str = " ".join(str(c) for c in sorted(self.deadwood_cards))
            lines.append(f"Deadwood ({self.deadwood_value}): {cards_str}")
        return "\n".join(lines)


def analyze_hand(cards: list[Card]) -> HandAnalysis:
    """Analyze a hand to find optimal melds and deadwood.

    Args:
        cards: List of cards in hand.

    Returns:
        HandAnalysis with melds, deadwood cards, and deadwood value.
    """
    melds, deadwood_value = find_optimal_melds(cards)

    # Find which cards are not in melds
    melded_cards: set[Card] = set()
    for meld in melds:
        melded_cards.update(meld.cards)

    deadwood_cards = [c for c in cards if c not in melded_cards]

    return HandAnalysis(
        melds=melds,
        deadwood_cards=deadwood_cards,
        deadwood_value=deadwood_value,
    )
