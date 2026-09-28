"""Tests for hand module."""

import pytest

from gin_rummy.models import Card, CardNotInHandError, Hand, Rank, Suit


class TestHand:
    def test_empty_hand(self):
        hand = Hand()
        assert len(hand) == 0
        assert str(hand) == "Empty hand"

    def test_create_with_cards(self):
        cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)]
        hand = Hand(cards)
        assert len(hand) == 2

    def test_add_card(self):
        hand = Hand()
        card = Card(Rank.ACE, Suit.SPADES)
        hand.add(card)
        assert len(hand) == 1
        assert card in hand

    def test_remove_card(self):
        card = Card(Rank.ACE, Suit.SPADES)
        hand = Hand([card])
        hand.remove(card)
        assert len(hand) == 0
        assert card not in hand

    def test_remove_card_not_in_hand_raises(self):
        hand = Hand()
        card = Card(Rank.ACE, Suit.SPADES)
        with pytest.raises(CardNotInHandError):
            hand.remove(card)

    def test_contains(self):
        card = Card(Rank.ACE, Suit.SPADES)
        hand = Hand([card])
        assert card in hand
        assert Card(Rank.KING, Suit.HEARTS) not in hand

    def test_iteration(self):
        cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)]
        hand = Hand(cards)
        iterated = list(hand)
        assert iterated == cards

    def test_getitem(self):
        cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)]
        hand = Hand(cards)
        assert hand[0] == cards[0]
        assert hand[1] == cards[1]

    def test_sort(self):
        cards = [
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.FIVE, Suit.CLUBS),
        ]
        hand = Hand(cards)
        hand.sort()
        assert hand[0] == Card(Rank.ACE, Suit.SPADES)
        assert hand[1] == Card(Rank.FIVE, Suit.CLUBS)
        assert hand[2] == Card(Rank.KING, Suit.HEARTS)

    def test_cards_property_returns_copy(self):
        cards = [Card(Rank.ACE, Suit.SPADES)]
        hand = Hand(cards)
        returned = hand.cards
        returned.append(Card(Rank.KING, Suit.HEARTS))
        assert len(hand) == 1  # Original unchanged

    def test_deadwood_total(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),  # 1
            Card(Rank.FIVE, Suit.HEARTS),  # 5
            Card(Rank.TEN, Suit.CLUBS),  # 10
            Card(Rank.KING, Suit.DIAMONDS),  # 10
        ]
        hand = Hand(cards)
        assert hand.deadwood_total == 26

    def test_str_representation(self):
        cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)]
        hand = Hand(cards)
        assert str(hand) == "A♠ K♥"

    def test_initializing_with_cards_makes_copy(self):
        original = [Card(Rank.ACE, Suit.SPADES)]
        hand = Hand(original)
        original.append(Card(Rank.KING, Suit.HEARTS))
        assert len(hand) == 1  # Hand unchanged
