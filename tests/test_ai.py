"""Tests for AI module."""

import pytest
from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.hand import Hand
from gin_rummy.card import Card, Suit, Rank


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
