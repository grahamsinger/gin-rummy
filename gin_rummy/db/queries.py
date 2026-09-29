"""Read-side queries for the history, stats and resume views."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from gin_rummy.db.connection import get_connection

if TYPE_CHECKING:
    pass


def get_recent_games(limit: int = 10, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get recent games."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("""SELECT * FROM games ORDER BY started_at DESC LIMIT ?""", (limit,))
        return cursor.fetchall()


def get_game_hands(game_id: int, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get all hands for a game."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("""SELECT * FROM hands WHERE game_id = ? ORDER BY hand_number""", (game_id,))
        return cursor.fetchall()


def get_hand_turns(hand_id: int, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get all turns for a hand."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("""SELECT * FROM turns WHERE hand_id = ? ORDER BY turn_number""", (hand_id,))
        return cursor.fetchall()


def get_ai_decisions_for_turn(turn_id: int, db_path: Path | None = None) -> list[sqlite3.Row]:
    """Get AI decisions for a turn."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("""SELECT * FROM ai_decisions WHERE turn_id = ? ORDER BY id""", (turn_id,))
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
        if row and row["total_hands"] > 0:
            stats["total_hands"] = row["total_hands"]
            stats["ai_wins"] = row["ai_wins"]
            stats["ai_win_rate"] = row["ai_wins"] / row["total_hands"]
            stats["ai_gins"] = row["ai_gins"]
            stats["ai_undercuts"] = row["ai_undercuts"]

        # Average deadwood when knocking
        cursor = conn.execute(
            """SELECT AVG(deadwood_after) as avg_knock_deadwood
               FROM turns
               WHERE did_knock = 1 AND player_name = 'Computer'"""
        )
        row = cursor.fetchone()
        if row and row["avg_knock_deadwood"]:
            stats["avg_knock_deadwood"] = row["avg_knock_deadwood"]

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
            {"name": row["player_name"], "total_hands": row["total_hands"], "win_rate": row["win_rate"] or 0.0}
            for row in rows
        ]


def delete_player_stats(player_name: str, db_path: Path | None = None) -> bool:
    """Delete all stats for a player. Returns True if deleted, False if player not found."""
    with get_connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM player_stats WHERE player_name = ?", (player_name,))
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
        hand_ids = [r["id"] for r in conn.execute("SELECT id FROM hands WHERE game_id = ?", (game_id,)).fetchall()]

        if hand_ids:
            placeholders = ",".join("?" * len(hand_ids))

            # Get turn IDs for these hands
            turn_ids = [
                r["id"]
                for r in conn.execute(f"SELECT id FROM turns WHERE hand_id IN ({placeholders})", hand_ids).fetchall()
            ]

            if turn_ids:
                turn_placeholders = ",".join("?" * len(turn_ids))
                # Delete ai_decisions for these turns
                conn.execute(
                    f"DELETE FROM ai_decisions WHERE turn_id IN ({turn_placeholders})",
                    turn_ids,
                )

            # Delete turns for these hands
            conn.execute(f"DELETE FROM turns WHERE hand_id IN ({placeholders})", hand_ids)

        # Delete hands for this game
        conn.execute("DELETE FROM hands WHERE game_id = ?", (game_id,))

        # Delete the game itself
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))

        conn.commit()
        return True


def get_resumable_game(game_id: int, db_path: Path | None = None) -> dict | None:
    """Fetch game settings and cumulative scores for an incomplete game.

    Returns None if the game is complete, doesn't exist, or has no hands with turns.
    """
    with get_connection(db_path) as conn:
        game = conn.execute(
            "SELECT * FROM games WHERE id = ? AND is_complete = 0",
            (game_id,),
        ).fetchone()
        if not game:
            return None

        # Check that game has at least one hand with turn data
        has_turns = conn.execute(
            """SELECT 1 FROM hands h
               JOIN turns t ON t.hand_id = h.id
               WHERE h.game_id = ?
               LIMIT 1""",
            (game_id,),
        ).fetchone()
        if not has_turns:
            return None

        # Compute cumulative scores from completed hands (those with turn data)
        p1 = game["player1_name"]
        p2 = game["player2_name"]
        scores = conn.execute(
            """SELECT
                   COALESCE(SUM(CASE WHEN h.winner_name = ?
                       THEN h.points_awarded ELSE 0 END), 0) AS p1_score,
                   COALESCE(SUM(CASE WHEN h.winner_name = ?
                       THEN h.points_awarded ELSE 0 END), 0) AS p2_score
               FROM hands h
               WHERE h.game_id = ?
                 AND h.ended_at IS NOT NULL
                 AND EXISTS (
                     SELECT 1 FROM turns t WHERE t.hand_id = h.id
                 )""",
            (p1, p2, game_id),
        ).fetchone()

        # Get last completed hand info (for dealer rotation)
        last_hand = conn.execute(
            """SELECT hand_number, dealer_name FROM hands
               WHERE game_id = ? AND ended_at IS NOT NULL
                 AND EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = hands.id)
               ORDER BY hand_number DESC LIMIT 1""",
            (game_id,),
        ).fetchone()

        # Match wins if applicable
        games_won = {}
        if game["match_mode"] and game["match_id"]:
            match_games = conn.execute(
                """SELECT winner_name, COUNT(*) as wins
                   FROM games
                   WHERE match_id = ? AND is_complete = 1 AND winner_name IS NOT NULL
                   GROUP BY winner_name""",
                (game["match_id"],),
            ).fetchall()
            games_won = {row["winner_name"]: row["wins"] for row in match_games}

        return {
            "game_id": game["id"],
            "player1_name": game["player1_name"],
            "player2_name": game["player2_name"],
            "oklahoma_gin": bool(game["oklahoma_gin"]),
            "spade_doubling": bool(game["spade_doubling"]),
            "game_mode": game["game_mode"],
            "target_score": game["target_score"],
            "ai_difficulty": game["ai_difficulty"],
            "match_mode": bool(game["match_mode"]),
            "match_id": game["match_id"],
            "started_at": game["started_at"],
            "p1_score": scores["p1_score"],
            "p2_score": scores["p2_score"],
            "last_hand_number": last_hand["hand_number"] if last_hand else 0,
            "last_dealer_name": last_hand["dealer_name"] if last_hand else game["player1_name"],
            "games_won": games_won,
        }


def get_incomplete_games(player_name: str | None = None, db_path: Path | None = None) -> list[dict]:
    """Get incomplete games that have at least one hand with turn data.

    Args:
        player_name: Filter by player name (optional)

    Returns:
        List of game summaries with computed scores, most recent first.
    """
    with get_connection(db_path) as conn:
        if player_name:
            games = conn.execute(
                """SELECT g.* FROM games g
                   WHERE g.is_complete = 0
                     AND (g.player1_name = ? OR g.player2_name = ?)
                     AND EXISTS (
                         SELECT 1 FROM hands h
                         JOIN turns t ON t.hand_id = h.id
                         WHERE h.game_id = g.id
                     )
                   ORDER BY g.started_at DESC""",
                (player_name, player_name),
            ).fetchall()
        else:
            games = conn.execute(
                """SELECT g.* FROM games g
                   WHERE g.is_complete = 0
                     AND EXISTS (
                         SELECT 1 FROM hands h
                         JOIN turns t ON t.hand_id = h.id
                         WHERE h.game_id = g.id
                     )
                   ORDER BY g.started_at DESC""",
            ).fetchall()

        results = []
        for game in games:
            # Compute cumulative scores
            scores = conn.execute(
                """SELECT
                       COALESCE(SUM(CASE WHEN h.winner_name = ? THEN h.points_awarded ELSE 0 END), 0) AS p1_score,
                       COALESCE(SUM(CASE WHEN h.winner_name = ? THEN h.points_awarded ELSE 0 END), 0) AS p2_score
                   FROM hands h
                   WHERE h.game_id = ?
                     AND h.ended_at IS NOT NULL
                     AND EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = h.id)""",
                (game["player1_name"], game["player2_name"], game["id"]),
            ).fetchone()

            # Count completed hands with turn data
            hand_count = conn.execute(
                """SELECT COUNT(*) as cnt FROM hands h
                   WHERE h.game_id = ?
                     AND h.ended_at IS NOT NULL
                     AND EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = h.id)""",
                (game["id"],),
            ).fetchone()["cnt"]

            results.append(
                {
                    "game_id": game["id"],
                    "player1_name": game["player1_name"],
                    "player2_name": game["player2_name"],
                    "started_at": game["started_at"],
                    "p1_score": scores["p1_score"],
                    "p2_score": scores["p2_score"],
                    "hand_count": hand_count,
                    "game_mode": game["game_mode"],
                    "target_score": game["target_score"],
                    "ai_difficulty": game["ai_difficulty"],
                    "oklahoma_gin": bool(game["oklahoma_gin"]),
                    "match_mode": bool(game["match_mode"]),
                }
            )

        return results


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

        return {"hands": deleted_hands, "games": deleted_games}
