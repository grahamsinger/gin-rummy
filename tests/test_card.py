"""Tests for card module."""

import pytest
from gin_rummy.models import Card, Suit, Rank


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


# Recorded from the pre-consolidation codecs (database.card_to_db_str and
# statistical._card_to_index) so the stored DB strings and the persisted
# statistics/learning indices keep loading unchanged.
_GOLDEN_CODES_AND_INDICES = (
    "AC=0 2C=1 3C=2 4C=3 5C=4 6C=5 7C=6 8C=7 9C=8 10C=9 JC=10 QC=11 KC=12 "
    "AD=13 2D=14 3D=15 4D=16 5D=17 6D=18 7D=19 8D=20 9D=21 10D=22 JD=23 QD=24 KD=25 "
    "AH=26 2H=27 3H=28 4H=29 5H=30 6H=31 7H=32 8H=33 9H=34 10H=35 JH=36 QH=37 KH=38 "
    "AS=39 2S=40 3S=41 4S=42 5S=43 6S=44 7S=45 8S=46 9S=47 10S=48 JS=49 QS=50 KS=51 "
)


class TestCodec:
    def test_code_and_index_match_the_stored_formats(self):
        for entry in _GOLDEN_CODES_AND_INDICES.split():
            code, index = entry.split("=")
            card = Card.parse(code)
            assert card.code == code
            assert card.index == int(index)
            assert Card.from_index(int(index)) == card

    def test_round_trip_all_52(self):
        deck = [Card(r, s) for s in Suit for r in Rank]
        assert len({c.code for c in deck}) == 52
        assert sorted(c.index for c in deck) == list(range(52))
        for card in deck:
            assert Card.parse(card.code) == card
            assert Card.from_index(card.index) == card

    def test_ten_alias_on_input_only(self):
        assert Card.parse("TS") == Card(Rank.TEN, Suit.SPADES)
        assert Card(Rank.TEN, Suit.SPADES).code == "10S"

    @pytest.mark.parametrize("bad", ["", "1", "10", "7X", "ZH", "107H", "7h", "as", None, 7])
    def test_invalid_codes_raise(self, bad):
        with pytest.raises(ValueError):
            Card.parse(bad)

    @pytest.mark.parametrize("bad", [-1, 52])
    def test_invalid_index_raises(self, bad):
        with pytest.raises(ValueError):
            Card.from_index(bad)
