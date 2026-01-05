"""Tests for AI module."""

import pytest
from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.models import Hand, Card, Suit, Rank


class TestBasicAI:
    def test_decide_draw_from_deck_when_no_discard(self):
        ai = BasicAI()
        hand = Hand([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.THREE, Suit.HEARTS),
        ])
        choice = ai.decide_draw(hand, None)
        assert choice == DrawChoice.DECK

    def test_decide_draw_takes_helpful_card(self):
        ai = BasicAI()
        # Hand with two aces - third ace would form a set
        hand = Hand([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.KING, Suit.CLUBS),
        ])
        # Discard is third ace
        discard = Card(Rank.ACE, Suit.CLUBS)
        choice = ai.decide_draw(hand, discard)
        assert choice == DrawChoice.DISCARD

    def test_decide_draw_ignores_unhelpful_card(self):
        ai = BasicAI()
        hand = Hand([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.THREE, Suit.HEARTS),
            Card(Rank.FIVE, Suit.CLUBS),
        ])
        # Discard doesn't help
        discard = Card(Rank.KING, Suit.DIAMONDS)
        choice = ai.decide_draw(hand, discard)
        assert choice == DrawChoice.DECK

    def test_decide_discard_removes_highest_deadwood(self):
        ai = BasicAI()
        hand = Hand([
            Card(Rank.ACE, Suit.SPADES),   # 1
            Card(Rank.TWO, Suit.HEARTS),   # 2
            Card(Rank.KING, Suit.CLUBS),   # 10 - highest deadwood
        ])
        discard = ai.decide_discard(hand)
        # Should discard King (highest deadwood not in meld)
        assert discard == Card(Rank.KING, Suit.CLUBS)

    def test_decide_discard_keeps_meld_cards(self):
        ai = BasicAI()
        hand = Hand([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),    # Part of set
            Card(Rank.KING, Suit.DIAMONDS),
        ])
        discard = ai.decide_discard(hand)
        # Should discard King, not break the set
        assert discard == Card(Rank.KING, Suit.DIAMONDS)

    def test_should_knock_when_able(self):
        ai = BasicAI()
        # Hand with 10 or less deadwood
        hand = Hand([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.TWO, Suit.DIAMONDS),  # 2 deadwood
        ])
        assert ai.should_knock(hand)

    def test_should_not_knock_when_high_deadwood(self):
        ai = BasicAI()
        hand = Hand([
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.QUEEN, Suit.HEARTS),
        ])  # 20 deadwood
        assert not ai.should_knock(hand)

    def test_make_turn_decision(self):
        ai = BasicAI()
        hand = Hand([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.KING, Suit.DIAMONDS),
        ])
        drawn = Card(Rank.KING, Suit.DIAMONDS)  # Already in hand conceptually

        discard, should_knock = ai.make_turn_decision(hand, None, drawn)

        assert discard in hand
        # With a set of aces and one king, deadwood is 10 - can knock
        assert isinstance(should_knock, bool)

    def test_never_pickup_and_immediately_discard(self):
        """Regression test for bug: AI picking up card and immediately discarding it.

        This bug occurred when decide_draw and decide_discard were not coordinated.
        decide_draw would think a card helps, but decide_discard would choose to
        discard that same card, wasting the turn and creating infinite loops.
        """
        ai = BasicAI()

        # Test many random hands to ensure the bug doesn't occur
        import random
        random.seed(42)

        for _ in range(100):
            # Generate random hand
            all_cards = [Card(rank, suit) for rank in Rank for suit in Suit]
            random.shuffle(all_cards)

            hand_cards = all_cards[:10]
            discard_top = all_cards[10]

            hand = Hand(hand_cards)

            # If AI decides to pick up from discard...
            choice = ai.decide_draw(hand, discard_top)
            if choice == DrawChoice.DISCARD:
                # Simulate picking it up
                test_hand = Hand(list(hand) + [discard_top])

                # AI should NEVER discard the card it just picked up
                discard = ai.decide_discard(test_hand)
                assert discard != discard_top, (
                    f"AI picked up {discard_top} and immediately discarded it! "
                    f"This wastes the turn and can create infinite loops."
                )
