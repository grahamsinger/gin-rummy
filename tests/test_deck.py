"""Tests for deck module."""

import pytest
from gin_rummy.deck import Deck, DeckEmptyError
from gin_rummy.card import Card, Suit, Rank


class TestDeck:
    def test_new_deck_has_52_cards(self):
        deck = Deck()
        assert len(deck) == 52

    def test_new_deck_contains_all_cards(self):
        deck = Deck()
        cards = [deck.draw() for _ in range(52)]
        card_set = set(cards)
        assert len(card_set) == 52

        # Verify all suit/rank combinations exist
        for suit in Suit:
            for rank in Rank:
                assert Card(rank, suit) in card_set

    def test_draw_returns_card(self):
        deck = Deck()
        card = deck.draw()
        assert isinstance(card, Card)

    def test_draw_reduces_count(self):
        deck = Deck()
        deck.draw()
        assert len(deck) == 51

    def test_draw_from_empty_raises(self):
        deck = Deck()
        for _ in range(52):
            deck.draw()

        with pytest.raises(DeckEmptyError):
            deck.draw()

    def test_draw_multiple(self):
        deck = Deck()
        cards = deck.draw_multiple(10)
        assert len(cards) == 10
        assert len(deck) == 42
        assert all(isinstance(c, Card) for c in cards)

    def test_draw_multiple_too_many_raises(self):
        deck = Deck()
        with pytest.raises(DeckEmptyError):
            deck.draw_multiple(53)

    def test_is_empty(self):
        deck = Deck()
        assert not deck.is_empty

        for _ in range(52):
            deck.draw()
        assert deck.is_empty

    def test_shuffle_changes_order(self):
        deck1 = Deck()
        deck2 = Deck()
        deck2.shuffle()

        # Draw all cards from both and compare
        cards1 = [deck1.draw() for _ in range(52)]
        cards2 = [deck2.draw() for _ in range(52)]

        # Extremely unlikely to be in same order after shuffle
        # (1 in 52! chance, effectively impossible)
        assert cards1 != cards2

    def test_shuffle_preserves_all_cards(self):
        deck = Deck()
        deck.shuffle()
        cards = [deck.draw() for _ in range(52)]
        card_set = set(cards)
        assert len(card_set) == 52
