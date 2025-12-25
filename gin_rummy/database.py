"""SQLite database for tracking game history."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Generator

from gin_rummy.config import get_config

if TYPE_CHECKING:
    from gin_rummy.card import Card


# Card serialization for database storage
# Uses ASCII format: "AS" = Ace of Spades, "10H" = Ten of Hearts
# This avoids Unicode escape issues in JSON and is more portable

def card_to_db_str(card: Card) -> str:
    """Serialize a Card to database format (ASCII, e.g., 'AS', '10H')."""
    from gin_rummy.card import Rank, Suit

    rank_map = {
        Rank.ACE: "A", Rank.TWO: "2", Rank.THREE: "3", Rank.FOUR: "4",
        Rank.FIVE: "5", Rank.SIX: "6", Rank.SEVEN: "7", Rank.EIGHT: "8",
        Rank.NINE: "9", Rank.TEN: "10", Rank.JACK: "J", Rank.QUEEN: "Q",
        Rank.KING: "K",
    }
    suit_map = {
        Suit.SPADES: "S", Suit.HEARTS: "H", Suit.DIAMONDS: "D", Suit.CLUBS: "C",
    }
    return f"{rank_map[card.rank]}{suit_map[card.suit]}"


def cards_to_db_list(cards: list[Card]) -> list[str]:
    """Serialize a list of Cards to database format."""
    return [card_to_db_str(c) for c in cards]


# Schema version for migrations
SCHEMA_VERSION = 1

SCHEMA = """
-- Track schema version for future migrations
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY
);

-- Individual games (a game consists of multiple hands until someone wins)
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    player1_name TEXT NOT NULL,
    player2_name TEXT NOT NULL,
    winner_name TEXT,
    final_score_p1 INTEGER,
    final_score_p2 INTEGER,
    is_complete INTEGER DEFAULT 0
);

-- Individual hands within a game
CREATE TABLE IF NOT EXISTS hands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    hand_number INTEGER NOT NULL,
    dealer_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    winner_name TEXT,
    points_awarded INTEGER,
    is_gin INTEGER DEFAULT 0,
    is_undercut INTEGER DEFAULT 0,
    is_draw INTEGER DEFAULT 0,
    FOREIGN KEY (game_id) REFERENCES games(id)
);

-- Individual turns within a hand
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hand_id INTEGER NOT NULL,
    turn_number INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    drew_from TEXT NOT NULL,  -- 'deck' or 'discard'
    card_drawn TEXT NOT NULL,
    card_discarded TEXT,
    did_knock INTEGER DEFAULT 0,
    cards_before TEXT NOT NULL,  -- JSON array of cards
    cards_after TEXT NOT NULL,   -- JSON array of cards
    deadwood_before INTEGER NOT NULL,
    deadwood_after INTEGER NOT NULL,
    FOREIGN KEY (hand_id) REFERENCES hands(id)
);

-- AI decision reasoning (optional detailed tracking)
CREATE TABLE IF NOT EXISTS ai_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL,
    decision_type TEXT NOT NULL,  -- 'draw', 'discard', 'knock'
    choice TEXT NOT NULL,         -- what was chosen
    reasoning TEXT,               -- why it was chosen
    options_considered TEXT,      -- JSON array of alternatives
    FOREIGN KEY (turn_id) REFERENCES turns(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_hands_game_id ON hands(game_id);
CREATE INDEX IF NOT EXISTS idx_turns_hand_id ON turns(hand_id);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_turn_id ON ai_decisions(turn_id);
CREATE INDEX IF NOT EXISTS idx_games_started_at ON games(started_at);
"""


def get_db_path() -> Path:
    """Get the database file path from config or default."""
    config = get_config()
    if hasattr(config, 'database') and hasattr(config.database, 'path'):
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
        if cursor.fetchone() is None:
            conn.execute("INSERT INTO schema_info (version) VALUES (?)", (SCHEMA_VERSION,))
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


class GameTracker:
    """Tracks game events to the database."""

    def __init__(self, db_path: Path | None = None):
        """Initialize tracker with optional custom db path."""
        self.db_path = db_path or get_db_path()
        init_db(self.db_path)
        self._game_id: int | None = None
        self._hand_id: int | None = None
        self._turn_number: int = 0
        self._hand_number: int = 0

    @property
    def game_id(self) -> int | None:
        return self._game_id

    @property
    def hand_id(self) -> int | None:
        return self._hand_id

    def start_game(self, player1_name: str, player2_name: str) -> int:
        """Record start of a new game. Returns game_id."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO games (started_at, player1_name, player2_name)
                   VALUES (?, ?, ?)""",
                (datetime.now().isoformat(), player1_name, player2_name)
            )
            conn.commit()
            assert cursor.lastrowid is not None
            self._game_id = cursor.lastrowid
            self._hand_number = 0
            return self._game_id

    def end_game(self, winner_name: str | None, score_p1: int, score_p2: int) -> None:
        """Record end of game."""
        if self._game_id is None:
            return
        with get_connection(self.db_path) as conn:
            conn.execute(
                """UPDATE games
                   SET ended_at = ?, winner_name = ?, final_score_p1 = ?,
                       final_score_p2 = ?, is_complete = 1
                   WHERE id = ?""",
                (datetime.now().isoformat(), winner_name, score_p1, score_p2, self._game_id)
            )
            conn.commit()

    def start_hand(self, dealer_name: str) -> int:
        """Record start of a new hand. Returns hand_id."""
        if self._game_id is None:
            raise ValueError("Must start a game before starting a hand")
        next_hand_number = self._hand_number + 1
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO hands (game_id, hand_number, dealer_name, started_at)
                   VALUES (?, ?, ?, ?)""",
                (self._game_id, next_hand_number, dealer_name, datetime.now().isoformat())
            )
            conn.commit()
            assert cursor.lastrowid is not None
            self._hand_number = next_hand_number
            self._turn_number = 0
            self._hand_id = cursor.lastrowid
            return self._hand_id

    def end_hand(
        self,
        winner_name: str | None,
        points: int,
        is_gin: bool = False,
        is_undercut: bool = False,
        is_draw: bool = False
    ) -> None:
        """Record end of hand."""
        if self._hand_id is None:
            return
        with get_connection(self.db_path) as conn:
            conn.execute(
                """UPDATE hands
                   SET ended_at = ?, winner_name = ?, points_awarded = ?,
                       is_gin = ?, is_undercut = ?, is_draw = ?
                   WHERE id = ?""",
                (
                    datetime.now().isoformat(), winner_name, points,
                    int(is_gin), int(is_undercut), int(is_draw), self._hand_id
                )
            )
            conn.commit()

    def record_turn(
        self,
        player_name: str,
        drew_from: str,
        card_drawn: str,
        card_discarded: str | None,
        did_knock: bool,
        cards_before: list[str],
        cards_after: list[str],
        deadwood_before: int,
        deadwood_after: int
    ) -> int:
        """Record a turn. Returns turn_id."""
        if self._hand_id is None:
            raise ValueError("Must start a hand before recording turns")
        next_turn_number = self._turn_number + 1
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO turns
                   (hand_id, turn_number, player_name, drew_from, card_drawn,
                    card_discarded, did_knock, cards_before, cards_after,
                    deadwood_before, deadwood_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self._hand_id, next_turn_number, player_name, drew_from,
                    card_drawn, card_discarded, int(did_knock),
                    json.dumps(cards_before), json.dumps(cards_after),
                    deadwood_before, deadwood_after
                )
            )
            conn.commit()
            assert cursor.lastrowid is not None
            self._turn_number = next_turn_number
            return cursor.lastrowid

    def record_ai_decision(
        self,
        turn_id: int,
        decision_type: str,
        choice: str,
        reasoning: str | None = None,
        options_considered: list[str] | None = None
    ) -> int:
        """Record an AI decision. Returns decision_id."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO ai_decisions
                   (turn_id, decision_type, choice, reasoning, options_considered)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    turn_id, decision_type, choice, reasoning,
                    json.dumps(options_considered) if options_considered else None
                )
            )
            conn.commit()
            assert cursor.lastrowid is not None
            return cursor.lastrowid


# Query helpers for analysis

def get_recent_games(limit: int = 10, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get recent games."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """SELECT * FROM games ORDER BY started_at DESC LIMIT ?""",
            (limit,)
        )
        return cursor.fetchall()


def get_game_hands(game_id: int, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get all hands for a game."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """SELECT * FROM hands WHERE game_id = ? ORDER BY hand_number""",
            (game_id,)
        )
        return cursor.fetchall()


def get_hand_turns(hand_id: int, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get all turns for a hand."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """SELECT * FROM turns WHERE hand_id = ? ORDER BY turn_number""",
            (hand_id,)
        )
        return cursor.fetchall()


def get_ai_decisions_for_turn(turn_id: int, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get AI decisions for a turn."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """SELECT * FROM ai_decisions WHERE turn_id = ? ORDER BY id""",
            (turn_id,)
        )
        return cursor.fetchall()


def get_ai_stats(db_path: Path | None = None) -> dict:
    """Get aggregate AI statistics."""
    with get_connection(db_path) as conn:
        stats = {}

        # Win rate
        cursor = conn.execute(
            """SELECT
                COUNT(*) as total_hands,
                SUM(CASE WHEN winner_name = 'Computer' THEN 1 ELSE 0 END) as ai_wins,
                SUM(CASE WHEN is_gin = 1 AND winner_name = 'Computer' THEN 1 ELSE 0 END) as ai_gins,
                SUM(CASE WHEN is_undercut = 1 AND winner_name != 'Computer' THEN 1 ELSE 0 END) as ai_undercuts
               FROM hands WHERE is_draw = 0"""
        )
        row = cursor.fetchone()
        if row and row['total_hands'] > 0:
            stats['total_hands'] = row['total_hands']
            stats['ai_wins'] = row['ai_wins']
            stats['ai_win_rate'] = row['ai_wins'] / row['total_hands']
            stats['ai_gins'] = row['ai_gins']
            stats['ai_undercuts'] = row['ai_undercuts']

        # Average deadwood when knocking
        cursor = conn.execute(
            """SELECT AVG(deadwood_after) as avg_knock_deadwood
               FROM turns
               WHERE did_knock = 1 AND player_name = 'Computer'"""
        )
        row = cursor.fetchone()
        if row and row['avg_knock_deadwood']:
            stats['avg_knock_deadwood'] = row['avg_knock_deadwood']

        return stats
