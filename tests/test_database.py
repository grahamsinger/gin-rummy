"""Tests for database.py against a temporary SQLite file."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gin_rummy.db import GameTracker, get_resumable_game
from gin_rummy.game import Game
from gin_rummy.models import Card, Rank, Suit


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def tracker(db_path: Path) -> GameTracker:
    return GameTracker(db_path)


def _hand_row(db_path: Path, hand_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM hands WHERE id = ?", (hand_id,)).fetchone()
    finally:
        conn.close()


def _game_in_discard_phase() -> Game:
    game = Game("Alice", "Bob")
    game.deal()
    game.discard_to_start(game.current_player.hand[0])
    game.draw_from_deck()
    return game


class TestEndHandFromResult:
    """B2: the DB row must come straight from the engine's RoundResult."""

    def test_records_normal_knock(self, tracker: GameTracker, db_path: Path):
        game = _game_in_discard_phase()
        knocker = game.current_player
        defender = game.opponent
        knocker.hand._cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.THREE, Suit.CLUBS)]  # 4 deadwood
        defender.hand._cards = [Card(Rank.FIVE, Suit.SPADES), Card(Rank.TEN, Suit.HEARTS)]  # 15 deadwood

        tracker.start_game("Alice", "Bob")
        hand_id = tracker.start_hand(dealer_name=game.dealer.name)
        result = game.knock()
        tracker.end_hand_from_result(result)

        row = _hand_row(db_path, hand_id)
        assert row["winner_name"] == knocker.name
        assert row["points_awarded"] == 11
        assert row["is_gin"] == 0
        assert row["is_undercut"] == 0
        assert row["is_draw"] == 0
        assert row["ended_at"] is not None

    def test_records_undercut_with_bonus(self, tracker: GameTracker, db_path: Path):
        game = _game_in_discard_phase()
        knocker = game.current_player
        defender = game.opponent
        knocker.hand._cards = [Card(Rank.FIVE, Suit.SPADES), Card(Rank.FIVE, Suit.HEARTS)]  # 10 deadwood
        defender.hand._cards = [Card(Rank.ACE, Suit.CLUBS), Card(Rank.TWO, Suit.CLUBS)]  # 3 deadwood

        tracker.start_game("Alice", "Bob")
        hand_id = tracker.start_hand(dealer_name=game.dealer.name)
        result = game.knock()
        tracker.end_hand_from_result(result)

        row = _hand_row(db_path, hand_id)
        assert result.is_undercut
        assert row["winner_name"] == defender.name
        assert row["points_awarded"] == game.undercut_bonus + 7
        assert row["is_undercut"] == 1

    def test_records_draw(self, tracker: GameTracker, db_path: Path):
        game = _game_in_discard_phase()
        tracker.start_game("Alice", "Bob")
        hand_id = tracker.start_hand(dealer_name=game.dealer.name)
        tracker.end_hand_from_result(game.get_draw_result())

        row = _hand_row(db_path, hand_id)
        assert row["winner_name"] is None
        assert row["points_awarded"] == 0
        assert row["is_draw"] == 1


class TestResumableGame:
    """B3: the dealer for resume must come from the last hand that has turns."""

    def test_last_dealer_ignores_hands_without_turns(self, tracker: GameTracker, db_path: Path):
        game_id = tracker.start_game("Alice", "Bob")

        # Hand 1: has a turn, ended.
        tracker.start_hand(dealer_name="Alice")
        tracker.record_turn(
            player_name="Bob",
            drew_from="deck",
            card_drawn="7H",
            card_discarded="KS",
            did_knock=False,
            cards_before=[],
            cards_after=[],
            deadwood_before=50,
            deadwood_after=40,
        )
        tracker.end_hand(winner_name="Bob", loser_name="Alice", points=12)

        # Hand 2: ended without any turns recorded (should not count).
        tracker.start_hand(dealer_name="Bob")
        tracker.end_hand(winner_name=None, loser_name=None, points=0, is_draw=True)

        info = get_resumable_game(game_id, db_path)
        assert info is not None
        assert info["last_hand_number"] == 1
        assert info["last_dealer_name"] == "Alice"
        assert info["p1_score"] == 0
        assert info["p2_score"] == 12
