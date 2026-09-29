#!/usr/bin/env python3
"""Stress test script for SQLite database with various row volumes."""

import json
import random
import sqlite3

# Import schema from main database module
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from gin_rummy.db import SCHEMA, SCHEMA_VERSION

STRESS_DB_PATH = Path(__file__).parent.parent / "stress_test.db"

# Card constants for generating realistic data
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]
ALL_CARDS = [f"{r}{s}" for r in RANKS for s in SUITS]

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank"]


def random_card() -> str:
    return random.choice(ALL_CARDS)


def random_hand(size: int = 10) -> list[str]:
    return random.sample(ALL_CARDS, size)


def random_deadwood() -> int:
    return random.randint(0, 100)


def init_stress_db() -> sqlite3.Connection:
    """Initialize the stress test database."""
    if STRESS_DB_PATH.exists():
        STRESS_DB_PATH.unlink()

    conn = sqlite3.connect(STRESS_DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO schema_info (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()
    return conn


def generate_data(conn: sqlite3.Connection, num_games: int, hands_per_game: int = 5, turns_per_hand: int = 15):
    """Generate test data with specified volume.

    Total rows created:
    - games: num_games
    - hands: num_games * hands_per_game
    - turns: num_games * hands_per_game * turns_per_hand
    """
    start_time = time.time()
    base_date = datetime.now() - timedelta(days=365)

    games_data = []
    hands_data = []
    turns_data = []

    game_id = 0
    hand_id = 0
    turn_id = 0

    for g in range(num_games):
        game_id = g + 1
        p1, p2 = random.sample(PLAYER_NAMES, 2)
        game_start = base_date + timedelta(hours=g)
        game_end = game_start + timedelta(minutes=random.randint(10, 60))
        winner = random.choice([p1, p2])
        score_p1 = random.randint(0, 150)
        score_p2 = random.randint(0, 150)

        games_data.append(
            (game_id, game_start.isoformat(), game_end.isoformat(), p1, p2, winner, score_p1, score_p2, 1)
        )

        for h in range(hands_per_game):
            hand_id += 1
            hand_start = game_start + timedelta(minutes=h * 5)
            hand_end = hand_start + timedelta(minutes=random.randint(2, 5))
            hand_winner = random.choice([p1, p2])
            points = random.randint(5, 50)
            is_gin = random.random() < 0.1
            is_undercut = random.random() < 0.15

            hands_data.append(
                (
                    hand_id,
                    game_id,
                    h + 1,
                    random.choice([p1, p2]),
                    hand_start.isoformat(),
                    hand_end.isoformat(),
                    hand_winner,
                    points,
                    int(is_gin),
                    int(is_undercut),
                    0,
                )
            )

            for t in range(turns_per_hand):
                turn_id += 1
                player = p1 if t % 2 == 0 else p2
                drew_from = random.choice(["deck", "discard"])
                cards_before = random_hand(10)
                cards_after = random_hand(10)
                dw_before = random_deadwood()
                dw_after = random_deadwood()
                did_knock = 1 if t == turns_per_hand - 1 and random.random() < 0.8 else 0

                turns_data.append(
                    (
                        turn_id,
                        hand_id,
                        t + 1,
                        player,
                        drew_from,
                        random_card(),
                        random_card(),
                        did_knock,
                        json.dumps(cards_before),
                        json.dumps(cards_after),
                        dw_before,
                        dw_after,
                    )
                )

    # Batch insert for performance
    conn.executemany(
        """INSERT INTO games (id, started_at, ended_at, player1_name, player2_name,
           winner_name, final_score_p1, final_score_p2, is_complete)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        games_data,
    )

    conn.executemany(
        """INSERT INTO hands (id, game_id, hand_number, dealer_name, started_at, ended_at,
           winner_name, points_awarded, is_gin, is_undercut, is_draw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        hands_data,
    )

    conn.executemany(
        """INSERT INTO turns (id, hand_id, turn_number, player_name, drew_from,
           card_drawn, card_discarded, did_knock, cards_before, cards_after,
           deadwood_before, deadwood_after)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        turns_data,
    )

    conn.commit()

    elapsed = time.time() - start_time
    total_rows = len(games_data) + len(hands_data) + len(turns_data)

    return {
        "games": len(games_data),
        "hands": len(hands_data),
        "turns": len(turns_data),
        "total": total_rows,
        "insert_time": elapsed,
    }


def run_benchmark_queries(conn: sqlite3.Connection) -> dict:
    """Run various queries and measure their execution time."""
    conn.row_factory = sqlite3.Row
    results = {}

    queries = {
        "count_all_turns": "SELECT COUNT(*) FROM turns",
        "count_all_games": "SELECT COUNT(*) FROM games",
        "recent_games_10": "SELECT * FROM games ORDER BY started_at DESC LIMIT 10",
        "recent_games_100": "SELECT * FROM games ORDER BY started_at DESC LIMIT 100",
        "hands_for_game": "SELECT * FROM hands WHERE game_id = 1",
        "turns_for_hand": "SELECT * FROM turns WHERE hand_id = 1",
        "aggregate_stats": """
            SELECT player_name,
                   COUNT(*) as total_turns,
                   AVG(deadwood_after) as avg_deadwood,
                   SUM(did_knock) as total_knocks
            FROM turns GROUP BY player_name
        """,
        "win_rate_by_player": """
            SELECT winner_name, COUNT(*) as wins
            FROM hands
            WHERE winner_name IS NOT NULL
            GROUP BY winner_name
        """,
        "join_games_hands": """
            SELECT g.id, g.player1_name, g.player2_name, COUNT(h.id) as hand_count
            FROM games g
            JOIN hands h ON g.id = h.game_id
            GROUP BY g.id
            LIMIT 100
        """,
        "complex_stats": """
            SELECT
                h.game_id,
                COUNT(DISTINCT h.id) as hands,
                COUNT(t.id) as turns,
                AVG(t.deadwood_after) as avg_deadwood,
                SUM(t.did_knock) as knocks
            FROM hands h
            JOIN turns t ON h.id = t.hand_id
            GROUP BY h.game_id
            LIMIT 50
        """,
        "search_by_player": """
            SELECT * FROM turns
            WHERE player_name = 'Alice'
            ORDER BY id DESC
            LIMIT 100
        """,
        "full_table_scan_filter": """
            SELECT COUNT(*) FROM turns
            WHERE deadwood_before > 50 AND deadwood_after < 30
        """,
    }

    for name, query in queries.items():
        start = time.time()
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        elapsed = time.time() - start
        results[name] = {"time_ms": elapsed * 1000, "rows_returned": len(rows)}

    return results


def format_results(insert_stats: dict, query_results: dict):
    """Format results for display."""
    print("\n" + "=" * 70)
    print("INSERT STATISTICS")
    print("=" * 70)
    print(f"  Games:     {insert_stats['games']:>12,}")
    print(f"  Hands:     {insert_stats['hands']:>12,}")
    print(f"  Turns:     {insert_stats['turns']:>12,}")
    print(f"  Total:     {insert_stats['total']:>12,}")
    print(f"  Time:      {insert_stats['insert_time']:>12.2f}s")
    print(f"  Rate:      {insert_stats['total'] / insert_stats['insert_time']:>12,.0f} rows/sec")

    print("\n" + "=" * 70)
    print("QUERY BENCHMARKS")
    print("=" * 70)
    print(f"  {'Query':<30} {'Time (ms)':>12} {'Rows':>10}")
    print("-" * 70)
    for name, stats in query_results.items():
        print(f"  {name:<30} {stats['time_ms']:>12.3f} {stats['rows_returned']:>10,}")


def run_stress_test(volumes: list[tuple[int, int, int]]):
    """Run stress tests at different volumes.

    Args:
        volumes: List of (num_games, hands_per_game, turns_per_hand) tuples
    """
    for num_games, hands_per_game, turns_per_hand in volumes:
        expected_total = num_games + (num_games * hands_per_game) + (num_games * hands_per_game * turns_per_hand)

        print("\n")
        print("#" * 70)
        print(f"  STRESS TEST: ~{expected_total:,} total rows")
        print(f"  ({num_games:,} games × {hands_per_game} hands × {turns_per_hand} turns)")
        print("#" * 70)

        conn = init_stress_db()

        print("\nGenerating data...")
        insert_stats = generate_data(conn, num_games, hands_per_game, turns_per_hand)

        print("Running benchmark queries...")
        query_results = run_benchmark_queries(conn)

        format_results(insert_stats, query_results)

        # Report db file size
        db_size = STRESS_DB_PATH.stat().st_size / (1024 * 1024)
        print(f"\n  Database file size: {db_size:.2f} MB")

        conn.close()


if __name__ == "__main__":
    # Test volumes: (games, hands_per_game, turns_per_hand)
    # Approximate total rows = games + (games * hands) + (games * hands * turns)
    test_volumes = [
        (100, 5, 15),  # ~8,100 rows
        (1000, 5, 15),  # ~81,000 rows
        (10000, 5, 15),  # ~810,000 rows
        (20000, 5, 15),  # ~1,620,000 rows
    ]

    print("SQLite Stress Test for Gin Rummy Database")
    print(f"Database location: {STRESS_DB_PATH}")

    run_stress_test(test_volumes)

    print("\n" + "=" * 70)
    print("STRESS TEST COMPLETE")
    print("=" * 70)
