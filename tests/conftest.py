"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

import gin_rummy.database as database


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every DB access at a per-test temporary file.

    GameTracker and get_connection resolve the path through
    database.get_db_path() at call time, so patching it keeps tests from
    touching the real game_history.db.
    """
    db_path = tmp_path / "test_game_history.db"
    monkeypatch.setattr(database, "get_db_path", lambda: db_path)
    return db_path
