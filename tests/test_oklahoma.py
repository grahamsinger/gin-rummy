"""Tests for Oklahoma Gin mode."""

import pytest
from gin_rummy.game import Game, GamePhase, InvalidActionError
from gin_rummy.models import Card, Suit, Rank


class TestOklahomaDeal:
    """Test Oklahoma Gin dealing procedure."""

    def test_oklahoma_deal_10_cards_each(self):
        """Oklahoma Gin deals 10 cards to each player (not 11)."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.deal()

        assert len(game.players[0].hand) == 10
        assert len(game.players[1].hand) == 10

    def test_oklahoma_upcard_set(self):
        """Oklahoma Gin sets an upcard."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.deal()

        assert game.upcard is not None
        assert isinstance(game.upcard, Card)

    def test_oklahoma_upcard_in_discard_pile(self):
        """Upcard becomes first card in discard pile."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.deal()

        assert len(game.discard_pile) == 1
        assert game.discard_pile[0] == game.upcard

    def test_oklahoma_skip_first_discard_phase(self):
        """Oklahoma Gin skips FIRST_DISCARD phase."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.deal()

        assert game.phase == GamePhase.DRAWING

    def test_oklahoma_non_dealer_goes_first(self):
        """Non-dealer goes first in Oklahoma Gin."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.deal()

        assert game.current_player == game.non_dealer


class TestKnockThreshold:
    """Test dynamic knock threshold based on upcard."""

    def test_knock_threshold_ace(self):
        """Ace upcard sets threshold to 0 (gin only)."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = Card(Rank.ACE, Suit.HEARTS)

        assert game.knock_threshold == 0

    def test_knock_threshold_two(self):
        """Two upcard sets threshold to 2."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = Card(Rank.TWO, Suit.CLUBS)

        assert game.knock_threshold == 2

    def test_knock_threshold_seven(self):
        """Seven upcard sets threshold to 7."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = Card(Rank.SEVEN, Suit.DIAMONDS)

        assert game.knock_threshold == 7

    def test_knock_threshold_ten(self):
        """Ten upcard sets threshold to 10."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = Card(Rank.TEN, Suit.SPADES)

        assert game.knock_threshold == 10

    def test_knock_threshold_jack(self):
        """Jack upcard sets threshold to 10."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = Card(Rank.JACK, Suit.HEARTS)

        assert game.knock_threshold == 10

    def test_knock_threshold_queen(self):
        """Queen upcard sets threshold to 10."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = Card(Rank.QUEEN, Suit.CLUBS)

        assert game.knock_threshold == 10

    def test_knock_threshold_king(self):
        """King upcard sets threshold to 10."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = Card(Rank.KING, Suit.DIAMONDS)

        assert game.knock_threshold == 10

    def test_standard_mode_uses_base_threshold(self):
        """Standard mode uses base knock threshold."""
        game = Game("Alice", "Bob", is_oklahoma_gin=False)
        # Base threshold from config should be 10
        assert game.knock_threshold == 10

    def test_oklahoma_no_upcard_uses_base_threshold(self):
        """Oklahoma mode without upcard uses base threshold."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.upcard = None

        assert game.knock_threshold == 10


class TestSpadeDoubling:
    """Test spade doubling functionality."""

    @staticmethod
    def _setup_gin_scenario(game: Game) -> tuple:
        """Deal and force a deterministic gin scenario.

        Alice: gin (three melds + a run of four, 0 deadwood).
        Bob: three runs (J-Q-K hearts, 2-3-4 clubs, 5-6-7 hearts) + 10 club
        = exactly 10 deadwood, nothing layoffable relevant (gin = no layoff).

        Expected base points: gin_bonus (25) + 10 = 35.
        """
        from gin_rummy.models import Hand

        alice = game.players[0]
        bob = game.players[1]

        alice.hand = Hand([
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.HEARTS),
            Card(Rank.FOUR, Suit.HEARTS),
            Card(Rank.SIX, Suit.DIAMONDS),
            Card(Rank.SEVEN, Suit.DIAMONDS),
            Card(Rank.EIGHT, Suit.DIAMONDS),
            Card(Rank.NINE, Suit.DIAMONDS),
        ])
        bob.hand = Hand([
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.QUEEN, Suit.HEARTS),
            Card(Rank.JACK, Suit.HEARTS),
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.THREE, Suit.CLUBS),
            Card(Rank.FOUR, Suit.CLUBS),
            Card(Rank.FIVE, Suit.HEARTS),
            Card(Rank.SIX, Suit.HEARTS),
            Card(Rank.SEVEN, Suit.HEARTS),
            Card(Rank.TEN, Suit.CLUBS),
        ])

        game.current_player_idx = 0
        game.phase = GamePhase.DISCARDING
        return alice, bob

    # Base points for the scenario: gin_bonus (25) + Bob's deadwood (10)
    EXPECTED_BASE_POINTS = 35

    def test_spade_doubling_enabled(self):
        """Points exactly doubled when upcard is spade and doubling enabled."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True, spade_doubling_enabled=True)
        game.deal()
        game.upcard = Card(Rank.FIVE, Suit.SPADES)
        alice, bob = self._setup_gin_scenario(game)

        result = game.knock()

        assert result.is_gin
        assert result.points == 2 * self.EXPECTED_BASE_POINTS
        assert alice.score == 2 * self.EXPECTED_BASE_POINTS

    def test_no_spade_doubling_when_disabled(self):
        """Points not doubled when spade doubling disabled, even on a spade."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True, spade_doubling_enabled=False)
        game.deal()
        game.upcard = Card(Rank.FIVE, Suit.SPADES)
        alice, bob = self._setup_gin_scenario(game)

        result = game.knock()

        assert result.is_gin
        assert result.points == self.EXPECTED_BASE_POINTS
        assert alice.score == self.EXPECTED_BASE_POINTS

    def test_no_spade_doubling_non_spade_upcard(self):
        """Points not doubled when upcard is not a spade."""
        game = Game("Alice", "Bob", is_oklahoma_gin=True, spade_doubling_enabled=True)
        game.deal()
        game.upcard = Card(Rank.FIVE, Suit.HEARTS)
        alice, bob = self._setup_gin_scenario(game)

        result = game.knock()

        assert result.is_gin
        assert result.points == self.EXPECTED_BASE_POINTS
        assert alice.score == self.EXPECTED_BASE_POINTS


class TestStandardModeUnchanged:
    """Ensure standard mode still works correctly."""

    def test_standard_deal_11_cards(self):
        """Standard mode deals 11 cards to non-dealer."""
        game = Game("Alice", "Bob", is_oklahoma_gin=False)
        game.deal()

        assert len(game.dealer.hand) == 10
        assert len(game.non_dealer.hand) == 11

    def test_standard_first_discard_phase(self):
        """Standard mode uses FIRST_DISCARD phase."""
        game = Game("Alice", "Bob", is_oklahoma_gin=False)
        game.deal()

        assert game.phase == GamePhase.FIRST_DISCARD

    def test_standard_no_upcard(self):
        """Standard mode doesn't set upcard."""
        game = Game("Alice", "Bob", is_oklahoma_gin=False)
        game.deal()

        assert game.upcard is None
        assert len(game.discard_pile) == 0
