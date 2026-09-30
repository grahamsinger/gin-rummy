"""Saved deep analyses (see gin_rummy.analysis.deep).

A result is stored whole as JSON, with the fields needed for listing and
lookup beside it. Re-analysing a position adds a row; lookups return the
one with the most samples.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from gin_rummy.db.connection import get_connection, init_db


def save_deep_analysis(result: dict[str, Any], db_path: Path | None = None) -> int:
    """Store an analysis result. Returns its id."""
    init_db(db_path)
    position = result["position"]
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO deep_analyses
                (created_at, seed, decision, position_key, best, confidence, samples, seconds, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                position.get("seed"),
                position["decision"],
                result["position_key"],
                result["best"],
                result["confidence"],
                result["samples"],
                result["seconds"],
                json.dumps(result),
            ),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def _load(row: Any) -> dict[str, Any]:
    result = json.loads(row["result_json"])
    result["id"] = row["id"]
    result["created_at"] = row["created_at"]
    return result


def find_deep_analysis(position_key: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """The saved analysis of this position with the most samples, or None."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM deep_analyses WHERE position_key = ? ORDER BY samples DESC, id DESC LIMIT 1",
            (position_key,),
        ).fetchone()
    return _load(row) if row else None


def get_deep_analysis(analysis_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM deep_analyses WHERE id = ?", (analysis_id,)).fetchone()
    return _load(row) if row else None


def list_deep_analyses(seed: int | None = None, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Saved analyses, newest first, without the full results."""
    init_db(db_path)
    query = "SELECT id, created_at, seed, decision, best, confidence, samples, seconds FROM deep_analyses"
    params: tuple = ()
    if seed is not None:
        query += " WHERE seed = ?"
        params = (seed,)
    with get_connection(db_path) as conn:
        rows = conn.execute(query + " ORDER BY id DESC", params).fetchall()
    return [dict(row) for row in rows]
