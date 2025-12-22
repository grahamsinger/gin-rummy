"""Tests for card module."""

import pytest
from gin_rummy.card import Card, Suit, Rank


class TestSuit:
    def test_symbols(self):
        assert Suit.CLUBS.symbol == "♣"
        assert Suit.DIAMONDS.symbol == "♦"
        assert Suit.HEARTS.symbol == "♥"
        assert Suit.SPADES.symbol == "♠"

    def test_all_suits_exist(self):
        assert len(Suit) == 4


class TestRank:
    def test_deadwood_values(self):
        assert Rank.ACE.deadwood_value == 1
        assert Rank.TWO.deadwood_value == 2
        assert Rank.NINE.deadwood_value == 9
        assert Rank.TEN.deadwood_value == 10
        assert Rank.JACK.deadwood_value == 10
        assert Rank.QUEEN.deadwood_value == 10
        assert Rank.KING.deadwood_value == 10

    def test_short_names(self):
        assert Rank.ACE.short_name == "A"
        assert Rank.TWO.short_name == "2"
        assert Rank.TEN.short_name == "10"
        assert Rank.JACK.short_name == "J"
        assert Rank.QUEEN.short_name == "Q"
        assert Rank.KING.short_name == "K"

    def test_all_ranks_exist(self):
        assert len(Rank) == 13

    def test_ordering(self):
        assert Rank.ACE < Rank.TWO
        assert Rank.TEN < Rank.JACK
        assert Rank.QUEEN < Rank.KING
        assert not Rank.KING < Rank.ACE


class TestCard:
    def test_creation(self):
        card = Card(Rank.ACE, Suit.SPADES)
        assert card.rank == Rank.ACE
        assert card.suit == Suit.SPADES

    def test_deadwood_value(self):
        assert Card(Rank.ACE, Suit.SPADES).deadwood_value == 1
        assert Card(Rank.FIVE, Suit.HEARTS).deadwood_value == 5
        assert Card(Rank.KING, Suit.CLUBS).deadwood_value == 10

    def test_str_representation(self):
        assert str(Card(Rank.ACE, Suit.SPADES)) == "A♠"
        assert str(Card(Rank.TEN, Suit.HEARTS)) == "10♥"
        assert str(Card(Rank.KING, Suit.CLUBS)) == "K♣"

    def test_immutability(self):
        card = Card(Rank.ACE, Suit.SPADES)
        with pytest.raises(AttributeError):
            card.rank = Rank.KING  # type: ignore[misc]

    def test_hashable(self):
        card1 = Card(Rank.ACE, Suit.SPADES)
        card2 = Card(Rank.ACE, Suit.SPADES)
        card_set = {card1, card2}
        assert len(card_set) == 1

    def test_equality(self):
        card1 = Card(Rank.ACE, Suit.SPADES)
        card2 = Card(Rank.ACE, Suit.SPADES)
        card3 = Card(Rank.ACE, Suit.HEARTS)
        assert card1 == card2
        assert card1 != card3

    def test_ordering_by_rank(self):
        ace = Card(Rank.ACE, Suit.SPADES)
        king = Card(Rank.KING, Suit.SPADES)
        assert ace < king

    def test_ordering_by_suit_when_same_rank(self):
        clubs = Card(Rank.ACE, Suit.CLUBS)
        spades = Card(Rank.ACE, Suit.SPADES)
        assert clubs < spades

    def test_sorting(self):
        cards = [
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.FIVE, Suit.DIAMONDS),
        ]
        sorted_cards = sorted(cards)
        assert sorted_cards[0] == Card(Rank.ACE, Suit.CLUBS)
        assert sorted_cards[1] == Card(Rank.ACE, Suit.SPADES)
        assert sorted_cards[2] == Card(Rank.FIVE, Suit.DIAMONDS)
        assert sorted_cards[3] == Card(Rank.KING, Suit.HEARTS)
