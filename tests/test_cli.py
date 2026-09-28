"""Tests for CLI round bookkeeping (no interactive input)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gin_rummy.cli import finish_round
from gin_rummy.database import GameTracker
from gin_rummy.game import Game
from gin_rummy.game_runner import TurnResult
from gin_rummy.models import Card, Rank, Suit


@pytest.fixture(autouse=True)
def no_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "")


def test_finish_round_records_engine_result(tmp_path: Path):
    """B2: CLI must record the RoundResult, not re-derive it from scores."""
    game = Game("Alice", "Bob")
    game.deal()
    game.discard_to_start(game.current_player.hand[0])
    game.draw_from_deck()
    knocker = game.current_player
    knocker.hand._cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.THREE, Suit.CLUBS)]  # 4
    game.opponent.hand._cards = [Card(Rank.FIVE, Suit.SPADES), Card(Rank.TEN, Suit.HEARTS)]  # 15
    result = game.knock()

    db_path = tmp_path / "cli.db"
    tracker = GameTracker(db_path)
    tracker.start_game("Alice", "Bob")
    hand_id = tracker.start_hand(dealer_name=game.dealer.name)

    finish_round(game, TurnResult.KNOCKED, result, tracker)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM hands WHERE id = ?", (hand_id,)).fetchone()
    conn.close()
    assert row["winner_name"] == knocker.name
    assert row["points_awarded"] == 11  # was always 0 before the fix
    assert row["is_gin"] == 0
    assert row["is_undercut"] == 0


def test_finish_round_without_tracker_is_safe():
    game = Game("Alice", "Bob")
    finish_round(game, TurnResult.DRAW, game.get_draw_result(), None)
