"""Turn-table recording invariants for the CLI and the web session.

Both UIs record every turn (human and AI) through the tracker. These tests
play a seeded round through each UI and check the rows written to the
`turns` table, so the recording code can be consolidated safely.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

import pytest

import gin_rummy.config as config_module
from gin_rummy.ai import BasicAI
from gin_rummy.config import Config
from gin_rummy.database import GameTracker
from gin_rummy.game import Game
from gin_rummy.models import Card


def _turn_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM ai_decisions d WHERE d.turn_id = t.id) AS n_decisions "
            "FROM turns t ORDER BY t.id"
        ).fetchall()
    finally:
        conn.close()


def _check_turn_rows(rows: list[sqlite3.Row], human_name: str, ai_name: str) -> None:
    """Every row must be internally consistent with the cards it names."""
    assert rows, "no turns were recorded"
    for row in rows:
        before = json.loads(row["cards_before"])
        after = json.loads(row["cards_after"])
        drawn, discarded = row["card_drawn"], row["card_discarded"]
        assert row["player_name"] in (human_name, ai_name)
        assert row["drew_from"] in ("deck", "discard")
        for code in [drawn, discarded, *before, *after]:
            Card.parse(code)  # every stored code is valid
        assert len(before) == 10 and len(after) == 10
        assert set(after) == (set(before) | {drawn}) - {discarded}, row["id"]
        assert 0 <= row["deadwood_after"] <= 98 and 0 <= row["deadwood_before"] <= 98
    knocks = [r for r in rows if r["did_knock"]]
    assert len(knocks) <= 1
    if knocks:
        assert knocks[0]["id"] == rows[-1]["id"], "the knock must be the last turn"
    # AI turns carry decision reasoning rows; human turns never do
    for row in rows:
        if row["player_name"] == ai_name:
            assert row["n_decisions"] >= 2, "AI turns record draw + discard/knock decisions"
        else:
            assert row["n_decisions"] == 0


@pytest.fixture
def quiet_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    cfg = Config()
    cfg.display.clear_screen = False
    cfg.display.ai_turn_delay = 0.0
    cfg.database.track_ai_decisions = True
    monkeypatch.setattr(config_module, "_config", cfg)
    return cfg


class TestCliRecording:
    def test_seeded_round_writes_consistent_turn_rows(self, quiet_config, isolated_db, monkeypatch, capsys):
        from gin_rummy import cli

        def scripted_input(prompt: str = "") -> str:
            """Answer by prompt text, so the script never depends on the deal."""
            if "Your choice" in prompt:
                return "1"  # draw from deck
            if "Card # to discard" in prompt or "Card to discard" in prompt:
                return "1"  # first listed card
            if "Knock?" in prompt:
                return "n"
            if "Discard anyway" in prompt:
                return "y"
            return ""  # "Press Enter" prompts

        monkeypatch.setattr("builtins.input", scripted_input)

        random.seed(7)
        game = Game("Human", "Computer")
        tracker = GameTracker(isolated_db)
        tracker.start_game("Human", "Computer")
        cli.play_round_vs_ai(game, BasicAI(quiet_config), human_player_idx=0, tracker=tracker)

        rows = _turn_rows(isolated_db)
        _check_turn_rows(rows, "Human", "Computer")
        assert {r["player_name"] for r in rows} == {"Human", "Computer"}


class TestWebRecording:
    def test_seeded_round_writes_consistent_turn_rows(self, quiet_config, isolated_db):
        from gin_rummy.web.game_session import GameSession

        random.seed(7)
        session = GameSession()
        session.new_game(player_name="Human", ai_difficulty="easy")

        for _ in range(200):
            state = session.get_state()
            if state["round_over"] or state["game_over"]:
                break
            if not state["your_turn"]:
                session.ai_turn()
            elif state["phase"] == "drawing":
                session.draw("deck")
            elif state["phase"] == "discarding":
                session.discard(state["hand"][0]["id"], knock=False)
            else:
                pytest.fail(f"unexpected phase {state['phase']!r}")
        else:
            pytest.fail("round did not finish")

        rows = _turn_rows(isolated_db)
        _check_turn_rows(rows, "Human", "Computer")
        assert {r["player_name"] for r in rows} == {"Human", "Computer"}
