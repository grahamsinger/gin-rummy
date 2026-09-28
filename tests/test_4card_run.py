"""Test that AI doesn't discard from the middle of a 4-card run."""

from gin_rummy.models import Card, Hand, Rank, Suit
from gin_rummy.ai import ContextAwareAI


def test_4card_run():
    """AI must not break a 4-card run from the middle.

    Hand: [7♠ 8♠ 9♠ 10♠] run + K♣ K♦ deadwood.
    Discarding 8♠ or 9♠ would shatter the run; the correct discard is a king.
    """
    cards = [
        Card(Rank.SEVEN, Suit.SPADES),
        Card(Rank.EIGHT, Suit.SPADES),
        Card(Rank.NINE, Suit.SPADES),
        Card(Rank.TEN, Suit.SPADES),
        Card(Rank.KING, Suit.CLUBS),
        Card(Rank.KING, Suit.DIAMONDS),
    ]
    hand = Hand(cards)

    ai = ContextAwareAI()
    discard = ai.decide_discard(hand)

    # The bug this test guards against: discarding from the middle of the run
    assert discard not in (
        Card(Rank.EIGHT, Suit.SPADES),
        Card(Rank.NINE, Suit.SPADES),
    ), f"AI discarded {discard} from the middle of a 4-card run"

    # The remaining hand must still contain a meld
    remaining = [c for c in cards if c != discard]
    remaining_analysis = Hand(remaining).analyze()
    assert len(remaining_analysis.melds) > 0, f"discarding {discard} left no melds in hand"

    # Optimal play: discard a king (deadwood 10 -> 10 vs breaking run -> 20+)
    assert discard.rank == Rank.KING, f"expected a king discard (pure deadwood), got {discard}"


def test_run_with_low_deadwood():
    """AI must not break a run even when the deadwood cards are low-value.

    Hand: [J♠ Q♠ K♠] run + A♠ + 2♣ deadwood (Ace is low, so A♠ does not
    extend the J-Q-K run). The low deadwood values must not tempt the AI
    into breaking the run.
    """
    cards = [
        Card(Rank.JACK, Suit.SPADES),
        Card(Rank.QUEEN, Suit.SPADES),
        Card(Rank.KING, Suit.SPADES),
        Card(Rank.ACE, Suit.SPADES),
        Card(Rank.TWO, Suit.CLUBS),
    ]
    hand = Hand(cards)

    ai = ContextAwareAI()
    discard = ai.decide_discard(hand)

    # Discard must come from the deadwood, not the run
    assert discard in (
        Card(Rank.ACE, Suit.SPADES),
        Card(Rank.TWO, Suit.CLUBS),
    ), f"AI discarded {discard} from the J-Q-K run instead of deadwood"

    remaining = [c for c in cards if c != discard]
    remaining_analysis = Hand(remaining).analyze()
    assert len(remaining_analysis.melds) > 0, f"discarding {discard} broke the run"
