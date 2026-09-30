"""Play a fully dealt position to the end of the hand and record how it ended."""

from __future__ import annotations

from dataclasses import dataclass

from gin_rummy.ai.mc.rollout import score_knock
from gin_rummy.analysis.style import Style, hand_shape, knocks, pick_discard, to_bits, to_cards, wants_discard
from gin_rummy.models import Card, analyze_hand

MAX_TURNS = 200  # far beyond any real hand; guards against an endless exchange of discards

ENDINGS = ("my_gin", "my_knock", "my_knock_undercut", "opp_gin", "opp_knock", "opp_knock_undercut", "deck_out")


@dataclass(frozen=True)
class Rules:
    knock_threshold: int = 10
    gin_bonus: int = 25
    undercut_bonus: int = 25
    min_deck_cards: int = 2


@dataclass(frozen=True)
class Outcome:
    """One play-out, from my side."""

    points: int
    ending: str  # one of ENDINGS
    turns: int  # turns played by both players together
    my_melds: tuple[str, ...]  # the melds I held at the end
    first_discard_taken: bool  # the opponent picked up the card on the pile at the start


def meld_names(cards: list[Card]) -> tuple[str, ...]:
    return tuple(sorted(" ".join(c.code for c in sorted(m.cards)) for m in analyze_hand(cards).melds))


def play_out(
    my_hand: list[Card],
    opp_hand: list[Card],
    deck: list[Card],
    pile: list[Card],
    public: set[Card] | frozenset[Card],
    my_turn: bool,
    my_style: Style,
    opp_style: Style,
    rules: Rules,
) -> Outcome:
    """Play until someone knocks or the deck runs out. Every argument is left untouched.

    deck: drawn from the end.
    public: every card that has been face up and is not in my hand; grows with each discard.
    """
    hands = {True: to_bits(my_hand), False: to_bits(opp_hand)}
    styles = {True: my_style, False: opp_style}
    stock = [card.index for card in deck]
    top = pile[-1].index if pile else None
    under: list[int] = []  # what lies below the top card, as far as this play-out has put it there
    seen = to_bits(public)
    first_discard_taken = False

    def finish(points: int, ending: str, turns: int) -> Outcome:
        return Outcome(points, ending, turns, meld_names(to_cards(hands[True])), first_discard_taken)

    for turn in range(MAX_TURNS):
        hand = hands[my_turn]
        style = styles[my_turn]

        blocked = None
        if top is not None and wants_discard(hand, top):
            hand |= 1 << top
            blocked = top
            top = under.pop() if under else None
            if turn == 0:
                first_discard_taken = True
        else:
            if len(stock) <= rules.min_deck_cards:
                return finish(0, "deck_out", turn)
            hand |= 1 << stock.pop()

        # A player's own cards are not public to them, even one they took from the pile
        discard = pick_discard(hand, seen & ~hand, style, blocked)
        hand &= ~(1 << discard)
        hands[my_turn] = hand
        if top is not None:
            under.append(top)
        top = discard
        seen |= 1 << discard

        if knocks(hand_shape(hand)[0], len(stock), style, rules.knock_threshold, rules.min_deck_cards):
            points, is_gin, is_undercut = score_knock(
                to_cards(hand),
                to_cards(hands[not my_turn]),
                rules.gin_bonus,
                rules.undercut_bonus,
                rules.knock_threshold,
            )
            who = "my" if my_turn else "opp"
            ending = f"{who}_gin" if is_gin else f"{who}_knock_undercut" if is_undercut else f"{who}_knock"
            return finish(points if my_turn else -points, ending, turn + 1)

        my_turn = not my_turn

    return finish(0, "deck_out", MAX_TURNS)
