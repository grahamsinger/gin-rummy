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

from gin_rummy.ai.outs import OutsCalculator
from gin_rummy.models import Card, Hand, Suit, analyze_hand
from gin_rummy.models.game_context import KnownCards


def parse_card(card_str: str) -> Card:
    """Parse a card string like '3s', 'KH' or 'TS' (case-insensitive) into a Card."""
    return Card.parse(card_str.strip().upper())


def parse_hand(hand_str: str) -> Hand:
    """Parse a space-separated string of cards into a Hand."""
    card_strs = hand_str.split()
    cards = [parse_card(s) for s in card_strs]
    return Hand(cards)


def parse_cards(cards_str: str) -> set[Card]:
    """Parse a space-separated string of cards into a set."""
    if not cards_str.strip():
        return set()
    return {parse_card(s) for s in cards_str.split()}


def display_hand_by_suit(hand: Hand) -> None:
    """Display hand organized by suit."""
    suits = {Suit.SPADES: [], Suit.HEARTS: [], Suit.DIAMONDS: [], Suit.CLUBS: []}
    for card in hand:
        suits[card.suit].append(card)

    for suit in [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]:
        cards = sorted(suits[suit], key=lambda c: c.rank.value)
        card_strs = [str(c) for c in cards] if cards else ["-"]
        print(f"  {suit.symbol}: {' '.join(card_strs)}")


def display_card_locations(known_cards: KnownCards) -> None:
    """Display a breakdown of card locations."""
    # Count unknown cards (52 total - all known locations)
    known_count = (
        len(known_cards.my_hand)
        + len(known_cards.opponent_hand_known)
        + (1 if known_cards.discard_top else 0)
        + len(known_cards.discard_buried)
    )
    unknown_count = 52 - known_count

    print("\n" + "-" * 60)
    print("CARD LOCATIONS")
    print("-" * 60)
    print(f"  My hand: {len(known_cards.my_hand)} cards")

    if known_cards.opponent_hand_known:
        opp_cards = sorted(known_cards.opponent_hand_known, key=lambda c: (c.rank.value, c.suit.value))
        print(f"  Opponent known: {len(known_cards.opponent_hand_known)} cards - {[str(c) for c in opp_cards]}")
    else:
        print("  Opponent known: 0 cards")

    if known_cards.discard_top:
        print(f"  Discard top: {known_cards.discard_top}")
    else:
        print("  Discard top: (empty)")

    if known_cards.discard_buried:
        buried = sorted(known_cards.discard_buried, key=lambda c: (c.rank.value, c.suit.value))
        print(f"  Discard buried: {len(known_cards.discard_buried)} cards - {[str(c) for c in buried]}")
    else:
        print("  Discard buried: 0 cards")

    print(f"  Unknown: {unknown_count} cards (in deck or opponent's initial hand)")
    print(f"  Dead cards: {len(known_cards.dead_cards)} (opponent known + buried)")


def analyze_outs(
    hand: Hand,
    dead_cards_str: str = "",
    opponent_known_str: str = "",
    discard_top_str: str = "",
) -> None:
    """Analyze and display outs for a hand."""
    # Parse card locations
    buried_cards = parse_cards(dead_cards_str)
    opponent_known = parse_cards(opponent_known_str)
    discard_top: Card | None = None
    if discard_top_str.strip():
        discard_top = parse_card(discard_top_str.strip())

    # Create KnownCards for unified tracking
    known_cards = KnownCards(
        my_hand=frozenset(hand),
        opponent_hand_known=frozenset(opponent_known),
        discard_top=discard_top,
        discard_buried=frozenset(buried_cards),
    )

    # Use KnownCards.dead_cards for outs calculation
    dead_cards = set(known_cards.dead_cards)

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

    # Show card location breakdown
    display_card_locations(known_cards)

    print("\n" + "-" * 60)
    print("MELD-COMPLETING OUTS")
    print("-" * 60)

    if analysis.meld_completing_outs:
        for out in sorted(analysis.meld_completing_outs, key=lambda o: (o.card.rank.value, o.card.suit.value)):
            dead_marker = " [DEAD]" if out.is_dead else ""
            print(f"  {out.card}: {out.description}{dead_marker}")
    else:
        print("  (none)")

    print("\n" + "-" * 60)
    print("PARTIAL OUTS (set-building, run-extending)")
    print("-" * 60)

    if analysis.partial_outs:
        for out in sorted(analysis.partial_outs, key=lambda o: (o.card.rank.value, o.card.suit.value)):
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
        epilog=__doc__,
    )
    parser.add_argument("hand", help="Space-separated card codes (e.g., '3S 8S 2H 2D 3D 6D KD 6C 8C KC')")
    parser.add_argument("--dead", "-d", default="", help="Buried discard pile cards as space-separated codes")
    parser.add_argument(
        "--opponent", "-o", default="", help="Cards known to be in opponent's hand (picked from discard)"
    )
    parser.add_argument("--discard-top", "-t", default="", help="Current top card of discard pile (available to take)")

    args = parser.parse_args()

    try:
        hand = parse_hand(args.hand)
        analyze_outs(hand, args.dead, args.opponent, args.discard_top)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
