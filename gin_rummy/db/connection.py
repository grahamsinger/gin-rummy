"""Database location, initialisation (with migrations) and connections."""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from gin_rummy.config import get_config
from gin_rummy.db.schema import SCHEMA, SCHEMA_VERSION

if TYPE_CHECKING:
    pass


def get_db_path() -> Path:
    """Get the database file path from config or default."""
    config = get_config()
    if hasattr(config, "database") and hasattr(config.database, "path"):
        return Path(config.database.path)
    # Default to game_history.db in current directory
    return Path("game_history.db")


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database with schema."""
    path = db_path or get_db_path()
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        # Set schema version if not exists
        cursor = conn.execute("SELECT version FROM schema_info LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_info (version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            current_version = row[0]
            if current_version < 3:
                # Migration: add game settings columns to games table
                for col_sql in [
                    "ALTER TABLE games ADD COLUMN oklahoma_gin INTEGER DEFAULT 0",
                    "ALTER TABLE games ADD COLUMN spade_doubling INTEGER DEFAULT 0",
                    "ALTER TABLE games ADD COLUMN game_mode TEXT",
                    "ALTER TABLE games ADD COLUMN target_score INTEGER",
                    "ALTER TABLE games ADD COLUMN ai_difficulty TEXT",
                    "ALTER TABLE games ADD COLUMN match_mode INTEGER DEFAULT 0",
                ]:
                    with contextlib.suppress(sqlite3.OperationalError):  # column already exists
                        conn.execute(col_sql)
                conn.execute("UPDATE schema_info SET version = ?", (3,))
                current_version = 3
            if current_version < 4:
                # Migration: add match_id column to games table
                with contextlib.suppress(sqlite3.OperationalError):  # column already exists
                    conn.execute("ALTER TABLE games ADD COLUMN match_id INTEGER")
                conn.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION,))
        conn.commit()


@contextmanager
def get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection context manager."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
