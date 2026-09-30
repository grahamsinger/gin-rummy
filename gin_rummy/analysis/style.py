"""Playing styles used to continue a hand after the decision under analysis.

The value of a move depends on how the hand is played afterwards, so a
play-out needs a policy for both players. A style only uses what a player
at the table can know: their own hand and the cards that have been face up
(every discard, which includes anything the other player picked up).

Play-outs run millions of these decisions, so the working form of a set
of cards is an int with one bit per card (bit `Card.index`)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from gin_rummy.models import Card, analyze_hand

ALL_CARDS: tuple[Card, ...] = tuple(Card.from_index(i) for i in range(52))
VALUE: tuple[int, ...] = tuple(card.deadwood_value for card in ALL_CARDS)
FULL_DECK = (1 << 52) - 1


def _neighbours(index: int) -> int:
    """Every card that could share a meld with this one: same rank, or same suit within two ranks."""
    suit, rank = divmod(index, 13)
    found = 0
    for other in range(52):
        other_suit, other_rank = divmod(other, 13)
        same_rank = other_rank == rank and other_suit != suit
        close = other_suit == suit and 0 < abs(other_rank - rank) <= 2
        if same_rank or close:
            found |= 1 << other
    return found


NEIGHBOURS: tuple[int, ...] = tuple(_neighbours(i) for i in range(52))
SAME_RANK: tuple[int, ...] = tuple(
    sum(1 << other for other in range(52) if other % 13 == i % 13 and other != i) for i in range(52)
)


@dataclass(frozen=True)
class Style:
    """How a player continues the hand.

    patience: the number of future draws a near meld is given to fill.
        0 plays for the lowest deadwood right now, which throws a pair away
        as soon as it holds the highest cards.
    knock_at: knock once deadwood is at or below this (gin always knocks).
    """

    name: str
    patience: int
    knock_at: int


GREEDY = Style("greedy", patience=0, knock_at=10)
PATIENT = Style("patient", patience=2, knock_at=10)
GIN_HUNTER = Style("gin hunter", patience=2, knock_at=0)
STYLES: dict[str, Style] = {s.name: s for s in (PATIENT, GREEDY, GIN_HUNTER)}


def to_bits(cards: Iterable[Card]) -> int:
    bits = 0
    for card in cards:
        bits |= 1 << card.index
    return bits


def to_indexes(bits: int) -> list[int]:
    indexes = []
    while bits:
        low = bits & -bits
        indexes.append(low.bit_length() - 1)
        bits ^= low
    return indexes


def to_cards(bits: int) -> list[Card]:
    return [ALL_CARDS[i] for i in to_indexes(bits)]


# Play-outs from one position meet the same hands again and again
_CACHE_LIMIT = 1_000_000
_shape_cache: dict[int, tuple[int, int, int]] = {}


def hand_shape(hand: int) -> tuple[int, int, int]:
    """(deadwood, value of the highest unmelded card, the unmelded cards) for the best melding of a hand."""
    shape = _shape_cache.get(hand)
    if shape is None:
        analysis = analyze_hand(to_cards(hand))
        highest = max((c.deadwood_value for c in analysis.deadwood_cards), default=0)
        shape = (analysis.deadwood_value, highest, to_bits(analysis.deadwood_cards))
        if len(_shape_cache) >= _CACHE_LIMIT:
            _shape_cache.clear()
        _shape_cache[hand] = shape
    return shape


def outs_of(kept: int, public: int) -> list[tuple[int, int]]:
    """(card index, deadwood saved) for every unseen card that would meld with `kept`.

    The saving counts the new meld and the discard that follows it.
    """
    base = hand_shape(kept)[0]
    reach = 0
    for index in to_indexes(kept):
        reach |= NEIGHBOURS[index]
    outs = []
    for index in to_indexes(reach & ~kept & ~public):
        bit = 1 << index
        total, highest, loose = hand_shape(kept | bit)
        if loose & bit:
            continue
        saving = base - (total - highest)  # the highest unmelded card is thrown after the draw
        if saving > 0:
            outs.append((index, saving))
    return outs


def near_meld_outs(loose: int, hidden: int) -> list[tuple[int, int]]:
    """(card index, deadwood saved) for every card in `hidden` that melds with two or more of the unmelded cards.

    The fast form of outs_of for play-outs: it looks only at the unmelded
    cards, so it misses the rare out that needs an existing meld rearranged.
    The saving counts the new meld and the discard that follows it.
    """
    reach = 0
    for index in to_indexes(loose):
        reach |= NEIGHBOURS[index]
    outs = []
    for index in to_indexes(reach & hidden):
        value = 0
        used = 0
        mates = SAME_RANK[index] & loose
        if mates.bit_count() >= 2:
            used = mates
            value = mates.bit_count() * VALUE[index]
        rank = index % 13
        run = 0
        step = 1
        while step <= rank and loose >> (index - step) & 1:
            run |= 1 << (index - step)
            step += 1
        step = 1
        while rank + step < 13 and loose >> (index + step) & 1:
            run |= 1 << (index + step)
            step += 1
        if run.bit_count() >= 2:
            run_value = sum(VALUE[i] for i in to_indexes(run))
            if run_value > value:
                used, value = run, run_value
        if value:
            thrown = max((VALUE[i] for i in to_indexes(loose & ~used)), default=0)
            outs.append((index, value + thrown))
    return outs


def potential_of(loose: int, hidden: int, patience: int) -> float:
    """Deadwood the unmelded cards can expect to shed through their outs within `patience` draws.

    hidden: the cards that could still arrive (not in the hand, never seen face up).
    """
    if patience <= 0 or not hidden:
        return 0.0
    arrives = 1.0 - (1.0 - 1.0 / hidden.bit_count()) ** patience
    return arrives * sum(saving for _, saving in near_meld_outs(loose, hidden))


def pick_discard(hand: int, public: int, style: Style, blocked: int | None) -> int:
    """The index of the card to throw from an 11-card hand: lowest deadwood after allowing for near melds."""
    total, _, loose = hand_shape(hand)
    candidates = loose
    if blocked is not None:
        candidates &= ~(1 << blocked)
    if not candidates:
        # Every free card is melded: break the meld that costs least
        candidates = hand if blocked is None else hand & ~(1 << blocked)
        return min(to_indexes(candidates), key=lambda i: (hand_shape(hand & ~(1 << i))[0], -VALUE[i], i))

    hidden = ~(hand | public) & FULL_DECK
    best = -1
    best_key: tuple[float, int, int] | None = None
    for index in to_indexes(candidates):
        # Throwing an unmelded card leaves the melds as they are
        score = total - VALUE[index] - potential_of(loose & ~(1 << index), hidden, style.patience)
        key = (score, -VALUE[index], index)  # ties: throw the higher card
        if best_key is None or key < best_key:
            best, best_key = index, key
    return best


def wants_discard(hand: int, top: int) -> bool:
    """Take the face-up card only when it goes straight into a meld and lowers the deadwood."""
    if not NEIGHBOURS[top] & hand:
        return False
    bit = 1 << top
    total, highest, loose = hand_shape(hand | bit)
    if loose & bit:
        return False
    return total - highest < hand_shape(hand)[0]


def knocks(deadwood: int, deck_left: int, style: Style, knock_threshold: int, min_deck_cards: int) -> bool:
    """Whether to end the hand with this deadwood."""
    if deadwood == 0:
        return True
    if deadwood > knock_threshold:
        return False
    if deck_left <= min_deck_cards + 2:
        return True  # the hand is about to be void
    return deadwood <= style.knock_at


# ---- The same decisions on Card objects, for callers outside the play-out loop


def live_outs(kept: list[Card], public: Iterable[Card]) -> list[tuple[Card, int]]:
    """Cards not yet seen that would meld with `kept`, with the deadwood each one saves."""
    return [(ALL_CARDS[i], saving) for i, saving in outs_of(to_bits(kept), to_bits(public))]


def potential(kept: list[Card], public: Iterable[Card], patience: int) -> float:
    bits = to_bits(kept)
    return potential_of(hand_shape(bits)[2], ~(bits | to_bits(public)) & FULL_DECK, patience)


def choose_discard(hand: list[Card], public: Iterable[Card], style: Style, blocked: Card | None) -> Card:
    index = pick_discard(to_bits(hand), to_bits(public), style, blocked.index if blocked else None)
    return ALL_CARDS[index]


def takes_discard(hand: list[Card], top: Card, style: Style) -> bool:
    return wants_discard(to_bits(hand), top.index)
