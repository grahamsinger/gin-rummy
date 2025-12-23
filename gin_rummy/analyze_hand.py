#!/usr/bin/env python3
"""Analyze a gin rummy hand and show outs.

Usage:
    uv run python -m gin_rummy.analyze_hand "3S 8S 2H 2D 3D 6D KD 6C 8C KC"

Cards are specified as: <rank><suit>
  Ranks: A 2 3 4 5 6 7 8 9 T J Q K
  Suits: S H D C (Spades, Hearts, Diamonds, Clubs)

Example cards: AS (Ace of Spades), TH (Ten of Hearts), KD (King of Diamonds)
"""

from __future__ import annotations

import argparse
import sys

from gin_rummy.card import Card, Suit, Rank
from gin_rummy.hand import Hand
from gin_rummy.context import OutsCalculator, OutType
from gin_rummy.melds import analyze_hand


RANK_MAP = {
    'A': Rank.ACE, '2': Rank.TWO, '3': Rank.THREE, '4': Rank.FOUR,
    '5': Rank.FIVE, '6': Rank.SIX, '7': Rank.SEVEN, '8': Rank.EIGHT,
    '9': Rank.NINE, 'T': Rank.TEN, '10': Rank.TEN,
    'J': Rank.JACK, 'Q': Rank.QUEEN, 'K': Rank.KING,
}

SUIT_MAP = {
    'S': Suit.SPADES, 'H': Suit.HEARTS, 'D': Suit.DIAMONDS, 'C': Suit.CLUBS,
}


def parse_card(card_str: str) -> Card:
    """Parse a card string like '3S' or 'KH' into a Card object."""
    card_str = card_str.upper().strip()
    if len(card_str) < 2:
        raise ValueError(f"Invalid card: {card_str}")

    # Handle 10 specially
    if card_str.startswith('10'):
        rank_str = '10'
        suit_str = card_str[2:]
    else:
        rank_str = card_str[:-1]
        suit_str = card_str[-1]

    if rank_str not in RANK_MAP:
        raise ValueError(f"Invalid rank: {rank_str} (use A,2-9,T,J,Q,K)")
    if suit_str not in SUIT_MAP:
        raise ValueError(f"Invalid suit: {suit_str} (use S,H,D,C)")

    return Card(RANK_MAP[rank_str], SUIT_MAP[suit_str])


def parse_hand(hand_str: str) -> Hand:
    """Parse a space-separated string of cards into a Hand."""
    card_strs = hand_str.split()
    cards = [parse_card(s) for s in card_strs]
    return Hand(cards)


def display_hand_by_suit(hand: Hand) -> None:
    """Display hand organized by suit."""
    suits = {Suit.SPADES: [], Suit.HEARTS: [], Suit.DIAMONDS: [], Suit.CLUBS: []}
    for card in hand:
        suits[card.suit].append(card)

    for suit in [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]:
        cards = sorted(suits[suit], key=lambda c: c.rank.value)
        card_strs = [str(c) for c in cards] if cards else ["-"]
        print(f"  {suit.symbol}: {' '.join(card_strs)}")


def analyze_outs(hand: Hand, dead_cards_str: str = "") -> None:
    """Analyze and display outs for a hand."""
    # Parse dead cards if provided
    dead_cards: set[Card] = set()
    if dead_cards_str:
        for card_str in dead_cards_str.split():
            dead_cards.add(parse_card(card_str))

    calc = OutsCalculator()
    analysis = calc.calculate_outs(hand, dead_cards=dead_cards)

    # Also analyze melds
    meld_analysis = analyze_hand(list(hand))

    print("\n" + "=" * 60)
    print("HAND ANALYSIS")
    print("=" * 60)

    print("\nHand:")
    display_hand_by_suit(hand)

    print(f"\nCurrent melds: {len(meld_analysis.melds)}")
    for meld in meld_analysis.melds:
        print(f"  {meld}")
    print(f"Deadwood: {meld_analysis.deadwood_value}")
    print(f"Deadwood cards: {[str(c) for c in meld_analysis.deadwood_cards]}")

    if dead_cards:
        print(f"\nDead cards: {[str(c) for c in dead_cards]}")

    print("\n" + "-" * 60)
    print("MELD-COMPLETING OUTS")
    print("-" * 60)

    if analysis.meld_completing_outs:
        for out in sorted(analysis.meld_completing_outs,
                         key=lambda o: (o.card.rank.value, o.card.suit.value)):
            dead_marker = " [DEAD]" if out.is_dead else ""
            print(f"  {out.card}: {out.description}{dead_marker}")
    else:
        print("  (none)")

    print("\n" + "-" * 60)
    print("PARTIAL OUTS (set-building, run-extending)")
    print("-" * 60)

    if analysis.partial_outs:
        for out in sorted(analysis.partial_outs,
                         key=lambda o: (o.card.rank.value, o.card.suit.value)):
            dead_marker = " [DEAD]" if out.is_dead else ""
            print(f"  {out.card} ({out.out_type.name}): {out.description}{dead_marker}")
    else:
        print("  (none)")

    print("\n" + "-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"  Meld-completing outs: {len(analysis.meld_completing_outs)}")
    print(f"  Partial outs: {len(analysis.partial_outs)}")
    print(f"  Total live outs: {analysis.live_out_count}")
    print(f"  Dead outs: {analysis.dead_out_count}")
    print(f"  Weighted value: {analysis.weighted_value:.1f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a gin rummy hand and show outs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "hand",
        help="Space-separated card codes (e.g., '3S 8S 2H 2D 3D 6D KD 6C 8C KC')"
    )
    parser.add_argument(
        "--dead", "-d",
        default="",
        help="Dead cards (discarded/seen) as space-separated codes"
    )

    args = parser.parse_args()

    try:
        hand = parse_hand(args.hand)
        analyze_outs(hand, args.dead)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
