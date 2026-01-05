#!/usr/bin/env python3
"""Test that AI doesn't discard from middle of 4-card run."""

from gin_rummy.models import Card, Hand, Rank, Suit
from gin_rummy.ai import ContextAwareAI


def test_4card_run():
    """Test with a 4-card run and deadwood."""
    print("Test: 4-card run discard behavior")
    print("="*60)

    # Hand: [7♠ 8♠ 9♠ 10♠] + K♣ K♦ (deadwood)
    cards = [
        Card(Rank.SEVEN, Suit.SPADES),
        Card(Rank.EIGHT, Suit.SPADES),
        Card(Rank.NINE, Suit.SPADES),
        Card(Rank.TEN, Suit.SPADES),
        Card(Rank.KING, Suit.CLUBS),
        Card(Rank.KING, Suit.DIAMONDS),
    ]

    hand = Hand(cards)
    analysis = hand.analyze()

    print(f"Hand: [7♠ 8♠ 9♠ 10♠] + K♣ K♦")
    print(f"Melds: {[[str(c) for c in m.cards] for m in analysis.melds]}")
    print(f"Deadwood: {[str(c) for c in analysis.deadwood_cards]}")
    print()

    ai = ContextAwareAI()
    discard = ai.decide_discard(hand)

    print(f"AI Discarded: {discard}")

    # Check what we discarded
    if discard in [Card(Rank.EIGHT, Suit.SPADES), Card(Rank.NINE, Suit.SPADES)]:
        print("❌ BUG: Discarded from MIDDLE of 4-card run (would break it)!")
        return False
    elif discard in [Card(Rank.SEVEN, Suit.SPADES), Card(Rank.TEN, Suit.SPADES)]:
        print("⚠️  Discarded from END of 4-card run (leaves valid 3-card run)")
        # Verify the remaining hand still has a valid run
        remaining = [c for c in cards if c != discard]
        remaining_analysis = Hand(remaining).analyze()
        if len(remaining_analysis.melds) > 0:
            print(f"   Remaining melds: {[[str(c) for c in m.cards] for m in remaining_analysis.melds]}")
            print("✅ GOOD: Remaining hand has valid meld")
            return True
        else:
            print("❌ BUG: No melds in remaining hand!")
            return False
    else:
        print(f"✅ GOOD: Discarded deadwood ({discard})")
        return True


def test_4card_run_middle_only():
    """Test where ONLY option is to discard from middle (worst case)."""
    print("\nTest: 4-card run where middle cards have lower value")
    print("="*60)

    # Hand: [J♠ Q♠ K♠ A♠] + 2♣ (low deadwood)
    # Aces are value 1, so discarding from run might seem attractive
    cards = [
        Card(Rank.JACK, Suit.SPADES),
        Card(Rank.QUEEN, Suit.SPADES),
        Card(Rank.KING, Suit.SPADES),
        Card(Rank.ACE, Suit.SPADES),  # Ace high in this run
        Card(Rank.TWO, Suit.CLUBS),
    ]

    hand = Hand(cards)
    analysis = hand.analyze()

    print(f"Hand: [J♠ Q♠ K♠ A♠] + 2♣")
    print(f"Melds: {[[str(c) for c in m.cards] for m in analysis.melds]}")
    print(f"Deadwood: {[str(c) for c in analysis.deadwood_cards]}")
    print()

    ai = ContextAwareAI()
    discard = ai.decide_discard(hand)

    print(f"AI Discarded: {discard}")

    # Check if it broke the run
    remaining = [c for c in cards if c != discard]
    remaining_analysis = Hand(remaining).analyze()

    if len(remaining_analysis.melds) == 0:
        print(f"❌ BUG: Broke the run! No melds remaining.")
        return False
    else:
        print(f"✅ GOOD: Remaining melds: {[[str(c) for c in m.cards] for m in remaining_analysis.melds]}")
        return True


if __name__ == "__main__":
    result1 = test_4card_run()
    result2 = test_4card_run_middle_only()

    print("\n" + "="*60)
    if result1 and result2:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
