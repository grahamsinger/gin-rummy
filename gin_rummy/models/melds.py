"""Meld detection and optimal deadwood calculation for Gin Rummy."""

from dataclasses import dataclass
from enum import Enum, auto
from itertools import combinations

from gin_rummy.models.card import Card, Rank, Suit


class MeldType(Enum):
    """Type of meld."""

    SET = auto()  # 3-4 cards of same rank
    RUN = auto()  # 3+ consecutive cards of same suit


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
    for rank_cards in by_rank.values():
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
    for suit_cards in by_suit.values():
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


def can_lay_off_on_meld(card: Card, meld: Meld) -> bool:
    """Check if a card can be laid off on an existing meld.

    Args:
        card: The card to potentially lay off.
        meld: The meld to lay off on.

    Returns:
        True if the card can extend the meld, False otherwise.
    """
    if meld.meld_type == MeldType.RUN:
        # For runs, card must be same suit and adjacent to either end
        meld_cards = meld.cards
        if card.suit != meld_cards[0].suit:
            return False

        # Get the rank values of the run endpoints
        sorted_by_rank = sorted(meld_cards, key=lambda c: c.rank.value)
        low_rank = sorted_by_rank[0].rank.value
        high_rank = sorted_by_rank[-1].rank.value

        # Card must be exactly one less than low or one more than high
        return card.rank.value == low_rank - 1 or card.rank.value == high_rank + 1

    elif meld.meld_type == MeldType.SET:
        # For sets, card must be same rank and different suit (not already in set)
        meld_cards = meld.cards
        if len(meld_cards) >= 4:
            # Set is full, can't add more
            return False

        # Must be same rank
        if card.rank != meld_cards[0].rank:
            return False

        # Must be a different suit (not already in the set)
        meld_suits = {c.suit for c in meld_cards}
        return card.suit not in meld_suits

    return False


def find_layoff_cards(defender_cards: list[Card], knocker_melds: list[Meld]) -> list[Card]:
    """Find all cards from defender's hand that can be laid off on knocker's melds.

    This handles chain layoffs where one card extends a run, enabling another
    card to also be laid off.

    Args:
        defender_cards: Cards in defender's hand (typically deadwood cards).
        knocker_melds: Melds from the knocker's hand.

    Returns:
        List of cards that can be laid off.
    """
    if not knocker_melds or not defender_cards:
        return []

    # A card may fit more than one meld (e.g. a 5 that extends both a run
    # and a set), and the wrong placement can block a chain layoff. Search
    # all placements to maximize the total deadwood value laid off.
    best_layoff: list[Card] = []
    best_value = -1
    seen: set[tuple[frozenset[Card], tuple[tuple[Card, ...], ...]]] = set()

    def search(
        remaining: list[Card],
        melds: list[tuple[MeldType, tuple[Card, ...]]],
        laid_off: list[Card],
        value: int,
    ) -> None:
        nonlocal best_layoff, best_value

        if value > best_value:
            best_value = value
            best_layoff = list(laid_off)

        state = (
            frozenset(remaining),
            tuple(sorted(cards for _, cards in melds)),
        )
        if state in seen:
            return
        seen.add(state)

        for card in remaining:
            for i, (meld_type, meld_cards) in enumerate(melds):
                if can_lay_off_on_meld(card, Meld(meld_cards, meld_type)):
                    new_melds = list(melds)
                    new_melds[i] = (meld_type, meld_cards + (card,))
                    search(
                        [c for c in remaining if c != card],
                        new_melds,
                        laid_off + [card],
                        value + card.deadwood_value,
                    )

    search(
        list(defender_cards),
        [(meld.meld_type, tuple(meld.cards)) for meld in knocker_melds],
        [],
        0,
    )

    return best_layoff


@dataclass
class LayoffResult:
    """Result of laying off cards on knocker's melds."""

    layoff_cards: list[Card]
    deadwood_before: int
    deadwood_after: int


def calculate_layoff(defender_cards: list[Card], knocker_melds: list[Meld]) -> LayoffResult:
    """Calculate defender's layoff and deadwood after laying off on knocker's melds.

    First analyzes defender's hand for their own melds, then allows layoff
    of remaining deadwood cards on knocker's melds.

    Args:
        defender_cards: All cards in defender's hand.
        knocker_melds: Melds from the knocker's hand.

    Returns:
        LayoffResult with layoff cards and deadwood before/after.
    """
    # First, find defender's own optimal melds
    analysis = analyze_hand(defender_cards)
    defender_deadwood_cards = analysis.deadwood_cards
    deadwood_before = analysis.deadwood_value

    # Find which deadwood cards can be laid off
    layoff_cards = find_layoff_cards(defender_deadwood_cards, knocker_melds)

    # Calculate remaining deadwood
    remaining_deadwood = [c for c in defender_deadwood_cards if c not in layoff_cards]
    deadwood_after = sum(c.deadwood_value for c in remaining_deadwood)

    return LayoffResult(
        layoff_cards=layoff_cards,
        deadwood_before=deadwood_before,
        deadwood_after=deadwood_after,
    )


def calculate_deadwood_after_layoff(defender_cards: list[Card], knocker_melds: list[Meld]) -> int:
    """Calculate defender's deadwood after laying off cards on knocker's melds.

    First analyzes defender's hand for their own melds, then allows layoff
    of remaining deadwood cards on knocker's melds.

    Args:
        defender_cards: All cards in defender's hand.
        knocker_melds: Melds from the knocker's hand.

    Returns:
        Defender's deadwood value after optimal layoff.
    """
    return calculate_layoff(defender_cards, knocker_melds).deadwood_after
