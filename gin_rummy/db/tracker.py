"""GameTracker: records a game, its hands, turns and AI decisions as they happen."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from gin_rummy.db.connection import get_connection, get_db_path, init_db

if TYPE_CHECKING:
    from gin_rummy.game import RoundResult


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
        match_id: int | None = None,
    ) -> int:
        """Record start of a new game. Returns game_id."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO games (started_at, player1_name, player2_name,
                       oklahoma_gin, spade_doubling, game_mode,
                       target_score, ai_difficulty, match_mode, match_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().isoformat(),
                    player1_name,
                    player2_name,
                    int(oklahoma_gin),
                    int(spade_doubling),
                    game_mode,
                    target_score,
                    ai_difficulty,
                    int(match_mode),
                    match_id,
                ),
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
                (datetime.now().isoformat(), winner_name, score_p1, score_p2, self._game_id),
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
                (self._game_id, next_hand_number, dealer_name, datetime.now().isoformat()),
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
                    datetime.now().isoformat(),
                    winner_name,
                    points,
                    int(is_gin),
                    int(is_undercut),
                    int(is_draw),
                    self._hand_id,
                ),
            )
            conn.commit()

        # Update player stats
        self.update_player_stats(
            winner_name, loser_name, points, is_gin, is_undercut, is_draw, knocker_name, winner_deadwood, loser_deadwood
        )

    def end_hand_from_result(self, result: RoundResult) -> None:
        """Record end of hand directly from the engine's RoundResult.

        This is the single source of truth for turning a RoundResult into a
        DB row; every UI (CLI, web, ...) should use it rather than
        re-deriving winner/points/gin/undercut from game state.
        """
        self.end_hand(
            winner_name=result.winner.name if result.winner else None,
            loser_name=result.loser.name if result.loser else None,
            points=result.points,
            is_gin=result.is_gin,
            is_undercut=result.is_undercut,
            is_draw=result.is_draw,
            knocker_name=result.knocker.name if result.knocker else None,
            winner_deadwood=result.winner_deadwood,
            loser_deadwood=result.loser_deadwood,
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
        deadwood_after: int,
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
                    self._hand_id,
                    next_turn_number,
                    player_name,
                    drew_from,
                    card_drawn,
                    card_discarded,
                    int(did_knock),
                    json.dumps(cards_before),
                    json.dumps(cards_after),
                    deadwood_before,
                    deadwood_after,
                ),
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
        options_considered: list[str] | None = None,
    ) -> int:
        """Record an AI decision. Returns decision_id."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO ai_decisions
                   (turn_id, decision_type, choice, reasoning, options_considered)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    turn_id,
                    decision_type,
                    choice,
                    reasoning,
                    json.dumps(options_considered) if options_considered else None,
                ),
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
                (self._hand_id,),
            ).fetchall()

            draw_stats_map = {
                row["player_name"]: {"deck": row["deck_draws"], "discard": row["discard_draws"]} for row in draw_stats
            }

            # Get knock deadwood if someone knocked
            knock_deadwood = None
            if knocker_name:
                knock_turn = conn.execute(
                    """SELECT deadwood_after FROM turns
                       WHERE hand_id = ? AND player_name = ? AND did_knock = 1
                       ORDER BY turn_number DESC LIMIT 1""",
                    (self._hand_id, knocker_name),
                ).fetchone()
                if knock_turn:
                    knock_deadwood = knock_turn["deadwood_after"]

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
                    (player_name, datetime.now().isoformat()),
                )

                # Build update query
                updates = {
                    "total_hands": 1,
                    "hands_won": 1 if is_winner and not is_draw else 0,
                    "hands_lost": 1 if not is_winner and not is_draw else 0,
                    "hands_drawn": 1 if is_draw else 0,
                    "gins": 1 if is_winner and is_gin else 0,
                    "undercuts_made": 1 if is_winner and is_undercut else 0,
                    "undercuts_suffered": 1 if not is_winner and is_undercut else 0,
                    "times_knocked": 1 if is_knocker else 0,
                    "times_opponent_knocked": 1 if knocker_name and not is_knocker else 0,
                    "total_points_scored": points if is_winner else 0,
                }

                # Add deadwood stats
                if is_winner and not is_draw:
                    updates["total_deadwood"] = winner_deadwood
                    updates["deadwood_count"] = 1
                elif not is_winner and not is_draw:
                    updates["total_deadwood"] = loser_deadwood
                    updates["deadwood_count"] = 1

                # Add draw stats
                if player_name in draw_stats_map:
                    updates["draws_from_deck"] = draw_stats_map[player_name]["deck"]
                    updates["draws_from_discard"] = draw_stats_map[player_name]["discard"]

                # Add knock deadwood if this player knocked
                if is_knocker and knock_deadwood is not None:
                    updates["total_knock_deadwood"] = knock_deadwood
                    updates["knock_count"] = 1

                # Execute update
                update_clauses = ", ".join(f"{k} = {k} + ?" for k in updates)
                update_clauses += ", last_updated = ?"
                values = list(updates.values()) + [datetime.now().isoformat(), player_name]

                conn.execute(
                    f"""UPDATE player_stats
                        SET {update_clauses}
                        WHERE player_name = ?""",
                    values,
                )

            conn.commit()

    def get_player_stats(self, player_name: str) -> dict | None:
        """Get lifetime statistics for a player."""
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM player_stats WHERE player_name = ?", (player_name,)).fetchone()

            if not row:
                return None

            stats = dict(row)

            # Calculate derived stats
            if stats["total_hands"] > 0:
                stats["win_rate"] = stats["hands_won"] / stats["total_hands"]
            else:
                stats["win_rate"] = 0.0

            if stats["deadwood_count"] > 0:
                stats["avg_deadwood"] = stats["total_deadwood"] / stats["deadwood_count"]
            else:
                stats["avg_deadwood"] = 0.0

            if stats["total_hands"] > 0:
                stats["avg_points_per_hand"] = stats["total_points_scored"] / stats["total_hands"]
            else:
                stats["avg_points_per_hand"] = 0.0

            if stats["hands_won"] > 0:
                stats["gin_rate"] = stats["gins"] / stats["hands_won"]
            else:
                stats["gin_rate"] = 0.0

            if stats["times_opponent_knocked"] > 0:
                stats["undercut_rate"] = stats["undercuts_made"] / stats["times_opponent_knocked"]
            else:
                stats["undercut_rate"] = 0.0

            if stats["total_hands"] > 0:
                stats["knock_aggression"] = stats["times_knocked"] / stats["total_hands"]
            else:
                stats["knock_aggression"] = 0.0

            total_draws = stats["draws_from_deck"] + stats["draws_from_discard"]
            if total_draws > 0:
                stats["deck_draw_rate"] = stats["draws_from_deck"] / total_draws
                stats["discard_draw_rate"] = stats["draws_from_discard"] / total_draws
            else:
                stats["deck_draw_rate"] = 0.0
                stats["discard_draw_rate"] = 0.0

            if stats["knock_count"] > 0:
                stats["avg_knock_deadwood"] = stats["total_knock_deadwood"] / stats["knock_count"]
            else:
                stats["avg_knock_deadwood"] = 0.0

            return stats


# Query helpers for analysis
