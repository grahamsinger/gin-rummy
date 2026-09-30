"""Schema migrations, one entry per version, applied in order by init_db.

Each entry is (version, statements). A statement that fails because the
column already exists is skipped, so re-running on a database created from
the current SCHEMA is safe.
"""

from __future__ import annotations

import contextlib
import sqlite3

MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        3,  # game settings columns on games
        [
            "ALTER TABLE games ADD COLUMN oklahoma_gin INTEGER DEFAULT 0",
            "ALTER TABLE games ADD COLUMN spade_doubling INTEGER DEFAULT 0",
            "ALTER TABLE games ADD COLUMN game_mode TEXT",
            "ALTER TABLE games ADD COLUMN target_score INTEGER",
            "ALTER TABLE games ADD COLUMN ai_difficulty TEXT",
            "ALTER TABLE games ADD COLUMN match_mode INTEGER DEFAULT 0",
        ],
    ),
    (
        4,  # match_id on games
        ["ALTER TABLE games ADD COLUMN match_id INTEGER"],
    ),
    (
        5,  # scenario_answers table; init_db has already created it from SCHEMA
        [],
    ),
    (
        6,  # deep_analyses table; init_db has already created it from SCHEMA
        [],
    ),
]


def apply_migrations(conn: sqlite3.Connection, current_version: int) -> int:
    """Bring a database at `current_version` up to the latest migration. Returns the new version."""
    for version, statements in MIGRATIONS:
        if current_version >= version:
            continue
        for sql in statements:
            with contextlib.suppress(sqlite3.OperationalError):  # column already exists
                conn.execute(sql)
        conn.execute("UPDATE schema_info SET version = ?", (version,))
        current_version = version
    return current_version
