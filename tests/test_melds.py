"""Tests for meld detection module."""

import pytest
from gin_rummy.melds import (
    Meld, MeldType, HandAnalysis,
    find_all_sets, find_all_runs, find_all_melds,
    find_optimal_melds, analyze_hand,
)
from gin_rummy.card import Card, Suit, Rank


class TestFindSets:
    def test_no_sets(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
        ]
        assert find_all_sets(cards) == []

    def test_set_of_three(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
        ]
        sets = find_all_sets(cards)
        assert len(sets) == 1
        assert sets[0].meld_type == MeldType.SET
        assert len(sets[0].cards) == 3

    def test_set_of_four(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.ACE, Suit.DIAMONDS),
        ]
        sets = find_all_sets(cards)
        # Should find 4 sets of 3 plus 1 set of 4
        assert len(sets) == 5
        set_of_four = [s for s in sets if len(s.cards) == 4]
        assert len(set_of_four) == 1

    def test_multiple_sets(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.KING, Suit.CLUBS),
        ]
        sets = find_all_sets(cards)
        # Two sets of 3
        assert len(sets) == 2


class TestFindRuns:
    def test_no_runs(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FIVE, Suit.SPADES),
        ]
        assert find_all_runs(cards) == []

    def test_run_of_three(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.THREE, Suit.SPADES),
        ]
        runs = find_all_runs(cards)
        assert len(runs) == 1
        assert runs[0].meld_type == MeldType.RUN
        assert len(runs[0].cards) == 3

    def test_run_of_four(self):
        cards = [
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.HEARTS),
            Card(Rank.FOUR, Suit.HEARTS),
        ]
        runs = find_all_runs(cards)
        # Should find: A-2-3, 2-3-4, A-2-3-4
        assert len(runs) == 3
        run_of_four = [r for r in runs if len(r.cards) == 4]
        assert len(run_of_four) == 1

    def test_run_different_suits_not_valid(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),  # Different suit
            Card(Rank.THREE, Suit.SPADES),
        ]
        assert find_all_runs(cards) == []

    def test_multiple_runs_different_suits(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.HEARTS),
        ]
        runs = find_all_runs(cards)
        assert len(runs) == 2


class TestFindOptimalMelds:
    def test_empty_hand(self):
        melds, deadwood = find_optimal_melds([])
        assert melds == []
        assert deadwood == 0

    def test_no_melds(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),   # 1
            Card(Rank.THREE, Suit.HEARTS), # 3
            Card(Rank.FIVE, Suit.CLUBS),   # 5
        ]
        melds, deadwood = find_optimal_melds(cards)
        assert melds == []
        assert deadwood == 9

    def test_single_set(self):
        cards = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.KING, Suit.CLUBS),
            Card(Rank.ACE, Suit.DIAMONDS),  # 1 deadwood
        ]
        melds, deadwood = find_optimal_melds(cards)
        assert len(melds) == 1
        assert deadwood == 1

    def test_single_run(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),  # 10 deadwood
        ]
        melds, deadwood = find_optimal_melds(cards)
        assert len(melds) == 1
        assert deadwood == 10

    def test_overlapping_melds_chooses_best(self):
        # Cards that could form either a set or run
        cards = [
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.THREE, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.FIVE, Suit.SPADES),
        ]
        # Set of 3s: 3+3+3 = 9 in meld, leaves 4+5 = 9 deadwood
        # Run 3-4-5: 3+4+5 = 12 in meld, leaves 3+3 = 6 deadwood
        # Run is better!
        melds, deadwood = find_optimal_melds(cards)
        assert deadwood == 6
        assert len(melds) == 1
        assert melds[0].meld_type == MeldType.RUN

    def test_gin_hand(self):
        # A gin hand with 0 deadwood
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.TWO, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.DIAMONDS),
            Card(Rank.FOUR, Suit.DIAMONDS),
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.KING, Suit.CLUBS),
            Card(Rank.KING, Suit.DIAMONDS),
        ]
        melds, deadwood = find_optimal_melds(cards)
        assert deadwood == 0
        assert len(melds) == 3


class TestAnalyzeHand:
    def test_analyze_returns_correct_structure(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.KING, Suit.DIAMONDS),
        ]
        analysis = analyze_hand(cards)
        assert isinstance(analysis, HandAnalysis)
        assert len(analysis.melds) == 1
        assert len(analysis.deadwood_cards) == 1
        assert analysis.deadwood_value == 10

    def test_analyze_str_output(self):
        cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
        ]
        analysis = analyze_hand(cards)
        output = str(analysis)
        assert "Melds:" in output
        assert "Set" in output


class TestMeld:
    def test_meld_str(self):
        meld = Meld(
            cards=(
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
            ),
            meld_type=MeldType.SET,
        )
        assert "Set" in str(meld)
        assert "A♠" in str(meld)

    def test_meld_size(self):
        meld = Meld(
            cards=(
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.TWO, Suit.SPADES),
                Card(Rank.THREE, Suit.SPADES),
            ),
            meld_type=MeldType.RUN,
        )
        assert meld.size == 3
