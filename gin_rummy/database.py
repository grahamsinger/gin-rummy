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
    from gin_rummy.models import Card


# Card serialization for database storage
# Uses ASCII format: "AS" = Ace of Spades, "10H" = Ten of Hearts
# This avoids Unicode escape issues in JSON and is more portable

def card_to_db_str(card: Card) -> str:
    """Serialize a Card to database format (ASCII, e.g., 'AS', '10H')."""
    from gin_rummy.models.card import Rank, Suit

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


def db_str_to_card(s: str) -> Card:
    """Parse a database format card string back to a Card object.

    Args:
        s: Card string like "AS", "10H", "KD"

    Returns:
        Card object
    """
    from gin_rummy.models.card import Card, Rank, Suit

    rank_map = {
        "A": Rank.ACE, "2": Rank.TWO, "3": Rank.THREE, "4": Rank.FOUR,
        "5": Rank.FIVE, "6": Rank.SIX, "7": Rank.SEVEN, "8": Rank.EIGHT,
        "9": Rank.NINE, "10": Rank.TEN, "J": Rank.JACK, "Q": Rank.QUEEN,
        "K": Rank.KING,
    }
    suit_map = {
        "S": Suit.SPADES, "H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS,
    }

    # Handle "10" specially (two-character rank)
    if s.startswith("10"):
        rank_str = "10"
        suit_str = s[2]
    else:
        rank_str = s[0]
        suit_str = s[1]

    return Card(rank_map[rank_str], suit_map[suit_str])


def db_list_to_cards(card_strs: list[str]) -> list[Card]:
    """Parse a list of database format card strings to Card objects."""
    return [db_str_to_card(s) for s in card_strs]


# Schema version for migrations
SCHEMA_VERSION = 3

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
    oklahoma_gin INTEGER DEFAULT 0,
    spade_doubling INTEGER DEFAULT 0,
    game_mode TEXT,
    target_score INTEGER,
    ai_difficulty TEXT,
    match_mode INTEGER DEFAULT 0,
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

-- Lifetime player statistics
CREATE TABLE IF NOT EXISTS player_stats (
    player_name TEXT PRIMARY KEY,
    -- Hand outcomes
    total_hands INTEGER DEFAULT 0,
    hands_won INTEGER DEFAULT 0,
    hands_lost INTEGER DEFAULT 0,
    hands_drawn INTEGER DEFAULT 0,
    -- Special outcomes
    gins INTEGER DEFAULT 0,                    -- Times went gin
    undercuts_made INTEGER DEFAULT 0,          -- Times undercut opponent
    undercuts_suffered INTEGER DEFAULT 0,      -- Times got undercut
    -- Knocking stats
    times_knocked INTEGER DEFAULT 0,           -- Times this player knocked
    times_opponent_knocked INTEGER DEFAULT 0,  -- Times opponent knocked
    -- Scoring
    total_points_scored INTEGER DEFAULT 0,
    total_deadwood INTEGER DEFAULT 0,          -- Sum of all final deadwoods
    deadwood_count INTEGER DEFAULT 0,          -- Number of times deadwood was recorded
    -- Draw source preference
    draws_from_deck INTEGER DEFAULT 0,
    draws_from_discard INTEGER DEFAULT 0,
    -- Knock threshold
    total_knock_deadwood INTEGER DEFAULT 0,    -- Sum of deadwood when knocking
    knock_count INTEGER DEFAULT 0,             -- Number of times knocked (for avg)
    -- Metadata
    last_updated TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_hands_game_id ON hands(game_id);
CREATE INDEX IF NOT EXISTS idx_turns_hand_id ON turns(hand_id);
CREATE INDEX IF NOT EXISTS idx_turns_knock_stats ON turns(did_knock, player_name);
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
                    try:
                        conn.execute(col_sql)
                    except sqlite3.OperationalError:
                        pass  # Column already exists
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

    def start_game(
        self,
        player1_name: str,
        player2_name: str,
        oklahoma_gin: bool = False,
        spade_doubling: bool = False,
        game_mode: str | None = None,
        target_score: int | None = None,
        ai_difficulty: str | None = None,
        match_mode: bool = False,
    ) -> int:
        """Record start of a new game. Returns game_id."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO games (started_at, player1_name, player2_name,
                       oklahoma_gin, spade_doubling, game_mode,
                       target_score, ai_difficulty, match_mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().isoformat(), player1_name, player2_name,
                    int(oklahoma_gin), int(spade_doubling), game_mode,
                    target_score, ai_difficulty, int(match_mode),
                )
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
        loser_name: str | None,
        points: int,
        is_gin: bool = False,
        is_undercut: bool = False,
        is_draw: bool = False,
        knocker_name: str | None = None,
        winner_deadwood: int = 0,
        loser_deadwood: int = 0,
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

        # Update player stats
        self.update_player_stats(
            winner_name, loser_name, points, is_gin, is_undercut,
            is_draw, knocker_name, winner_deadwood, loser_deadwood
        )

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

    def update_player_stats(
        self,
        winner_name: str | None,
        loser_name: str | None,
        points: int,
        is_gin: bool,
        is_undercut: bool,
        is_draw: bool,
        knocker_name: str | None,
        winner_deadwood: int,
        loser_deadwood: int,
    ) -> None:
        """Update lifetime statistics for both players after a hand."""
        if self._hand_id is None:
            return

        with get_connection(self.db_path) as conn:
            # Get draw stats for this hand (from turns table)
            draw_stats = conn.execute(
                """SELECT player_name,
                          SUM(CASE WHEN drew_from = 'deck' THEN 1 ELSE 0 END) as deck_draws,
                          SUM(CASE WHEN drew_from = 'discard' THEN 1 ELSE 0 END) as discard_draws
                   FROM turns
                   WHERE hand_id = ?
                   GROUP BY player_name""",
                (self._hand_id,)
            ).fetchall()

            draw_stats_map = {
                row['player_name']: {
                    'deck': row['deck_draws'],
                    'discard': row['discard_draws']
                }
                for row in draw_stats
            }

            # Get knock deadwood if someone knocked
            knock_deadwood = None
            if knocker_name:
                knock_turn = conn.execute(
                    """SELECT deadwood_after FROM turns
                       WHERE hand_id = ? AND player_name = ? AND did_knock = 1
                       ORDER BY turn_number DESC LIMIT 1""",
                    (self._hand_id, knocker_name)
                ).fetchone()
                if knock_turn:
                    knock_deadwood = knock_turn['deadwood_after']

            # Update stats for both players
            players = []
            if is_draw:
                # Both players in a draw
                if winner_name:
                    players.append(winner_name)
                if loser_name:
                    players.append(loser_name)
            else:
                # Winner and loser
                if winner_name:
                    players.append(winner_name)
                if loser_name:
                    players.append(loser_name)

            for player_name in players:
                is_winner = player_name == winner_name
                is_knocker = player_name == knocker_name

                # Initialize player stats if not exists
                conn.execute(
                    """INSERT OR IGNORE INTO player_stats (player_name, last_updated)
                       VALUES (?, ?)""",
                    (player_name, datetime.now().isoformat())
                )

                # Build update query
                updates = {
                    'total_hands': 1,
                    'hands_won': 1 if is_winner and not is_draw else 0,
                    'hands_lost': 1 if not is_winner and not is_draw else 0,
                    'hands_drawn': 1 if is_draw else 0,
                    'gins': 1 if is_winner and is_gin else 0,
                    'undercuts_made': 1 if is_winner and is_undercut else 0,
                    'undercuts_suffered': 1 if not is_winner and is_undercut else 0,
                    'times_knocked': 1 if is_knocker else 0,
                    'times_opponent_knocked': 1 if knocker_name and not is_knocker else 0,
                    'total_points_scored': points if is_winner else 0,
                }

                # Add deadwood stats
                if is_winner and not is_draw:
                    updates['total_deadwood'] = winner_deadwood
                    updates['deadwood_count'] = 1
                elif not is_winner and not is_draw:
                    updates['total_deadwood'] = loser_deadwood
                    updates['deadwood_count'] = 1

                # Add draw stats
                if player_name in draw_stats_map:
                    updates['draws_from_deck'] = draw_stats_map[player_name]['deck']
                    updates['draws_from_discard'] = draw_stats_map[player_name]['discard']

                # Add knock deadwood if this player knocked
                if is_knocker and knock_deadwood is not None:
                    updates['total_knock_deadwood'] = knock_deadwood
                    updates['knock_count'] = 1

                # Execute update
                update_clauses = ', '.join(f"{k} = {k} + ?" for k in updates.keys())
                update_clauses += ', last_updated = ?'
                values = list(updates.values()) + [datetime.now().isoformat(), player_name]

                conn.execute(
                    f"""UPDATE player_stats
                        SET {update_clauses}
                        WHERE player_name = ?""",
                    values
                )

            conn.commit()

    def get_player_stats(self, player_name: str) -> dict | None:
        """Get lifetime statistics for a player."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM player_stats WHERE player_name = ?",
                (player_name,)
            ).fetchone()

            if not row:
                return None

            stats = dict(row)

            # Calculate derived stats
            if stats['total_hands'] > 0:
                stats['win_rate'] = stats['hands_won'] / stats['total_hands']
            else:
                stats['win_rate'] = 0.0

            if stats['deadwood_count'] > 0:
                stats['avg_deadwood'] = stats['total_deadwood'] / stats['deadwood_count']
            else:
                stats['avg_deadwood'] = 0.0

            if stats['total_hands'] > 0:
                stats['avg_points_per_hand'] = stats['total_points_scored'] / stats['total_hands']
            else:
                stats['avg_points_per_hand'] = 0.0

            if stats['hands_won'] > 0:
                stats['gin_rate'] = stats['gins'] / stats['hands_won']
            else:
                stats['gin_rate'] = 0.0

            if stats['times_opponent_knocked'] > 0:
                stats['undercut_rate'] = stats['undercuts_made'] / stats['times_opponent_knocked']
            else:
                stats['undercut_rate'] = 0.0

            if stats['total_hands'] > 0:
                stats['knock_aggression'] = stats['times_knocked'] / stats['total_hands']
            else:
                stats['knock_aggression'] = 0.0

            total_draws = stats['draws_from_deck'] + stats['draws_from_discard']
            if total_draws > 0:
                stats['deck_draw_rate'] = stats['draws_from_deck'] / total_draws
                stats['discard_draw_rate'] = stats['draws_from_discard'] / total_draws
            else:
                stats['deck_draw_rate'] = 0.0
                stats['discard_draw_rate'] = 0.0

            if stats['knock_count'] > 0:
                stats['avg_knock_deadwood'] = stats['total_knock_deadwood'] / stats['knock_count']
            else:
                stats['avg_knock_deadwood'] = 0.0

            return stats


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


def get_all_players(db_path: Path | None = None) -> list[dict]:
    """Get list of all players who have stats."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """SELECT
                player_name,
                total_hands,
                CAST(hands_won AS REAL) / NULLIF(total_hands, 0) as win_rate
               FROM player_stats
               WHERE total_hands > 0
               ORDER BY player_name"""
        )
        rows = cursor.fetchall()
        return [
            {
                'name': row['player_name'],
                'total_hands': row['total_hands'],
                'win_rate': row['win_rate'] or 0.0
            }
            for row in rows
        ]


def delete_player_stats(player_name: str, db_path: Path | None = None) -> bool:
    """Delete all stats for a player. Returns True if deleted, False if player not found."""
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM player_stats WHERE player_name = ?",
            (player_name,)
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_game(game_id: int, db_path: Path | None = None) -> bool:
    """Delete a game and all related data (hands, turns, ai_decisions).

    Returns True if the game existed and was deleted, False otherwise.
    """
    with get_connection(db_path) as conn:
        # Check game exists
        row = conn.execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        if not row:
            return False

        # Get hand IDs for this game
        hand_ids = [
            r['id'] for r in conn.execute(
                "SELECT id FROM hands WHERE game_id = ?", (game_id,)
            ).fetchall()
        ]

        if hand_ids:
            placeholders = ','.join('?' * len(hand_ids))

            # Get turn IDs for these hands
            turn_ids = [
                r['id'] for r in conn.execute(
                    f"SELECT id FROM turns WHERE hand_id IN ({placeholders})", hand_ids
                ).fetchall()
            ]

            if turn_ids:
                turn_placeholders = ','.join('?' * len(turn_ids))
                # Delete ai_decisions for these turns
                conn.execute(
                    f"DELETE FROM ai_decisions WHERE turn_id IN ({turn_placeholders})",
                    turn_ids,
                )

            # Delete turns for these hands
            conn.execute(
                f"DELETE FROM turns WHERE hand_id IN ({placeholders})", hand_ids
            )

        # Delete hands for this game
        conn.execute("DELETE FROM hands WHERE game_id = ?", (game_id,))

        # Delete the game itself
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))

        conn.commit()
        return True


def cleanup_empty_games(db_path: Path | None = None) -> dict[str, int]:
    """Remove games and hands that have no turn data.

    This cleans up abandoned games where the human never made a move.

    Returns:
        Dict with counts of deleted items: {'hands': N, 'games': N}
    """
    with get_connection(db_path) as conn:
        # First, delete hands that have no turns
        cursor = conn.execute(
            """DELETE FROM hands
               WHERE id NOT IN (SELECT DISTINCT hand_id FROM turns)"""
        )
        deleted_hands = cursor.rowcount

        # Then, delete games that have no hands remaining
        cursor = conn.execute(
            """DELETE FROM games
               WHERE id NOT IN (SELECT DISTINCT game_id FROM hands)"""
        )
        deleted_games = cursor.rowcount

        conn.commit()

        return {'hands': deleted_hands, 'games': deleted_games}
