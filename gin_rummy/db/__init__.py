"""SQLite game history.

- schema: the schema text and its version
- connection: database path, init_db (with migrations), get_connection
- tracker: GameTracker, which records games as they are played
- queries: the read side (history, stats, resumable games)
- scenario_stats: scenario-quiz answers and all-time agreement totals
- deep_analyses: saved deep-analysis results
"""

from gin_rummy.db.connection import get_connection, get_db_path, init_db
from gin_rummy.db.deep_analyses import find_deep_analysis, get_deep_analysis, list_deep_analyses, save_deep_analysis
from gin_rummy.db.queries import (
    cleanup_empty_games,
    delete_game,
    delete_player_stats,
    get_ai_decisions_for_turn,
    get_ai_stats,
    get_all_players,
    get_game_hands,
    get_hand_turns,
    get_incomplete_games,
    get_recent_games,
    get_resumable_game,
)
from gin_rummy.db.scenario_stats import get_scenario_totals, record_scenario_answers
from gin_rummy.db.schema import SCHEMA, SCHEMA_VERSION
from gin_rummy.db.tracker import GameTracker

__all__ = [
    "SCHEMA",
    "SCHEMA_VERSION",
    "GameTracker",
    "cleanup_empty_games",
    "delete_game",
    "delete_player_stats",
    "find_deep_analysis",
    "get_ai_decisions_for_turn",
    "get_ai_stats",
    "get_all_players",
    "get_connection",
    "get_db_path",
    "get_deep_analysis",
    "get_game_hands",
    "get_hand_turns",
    "get_incomplete_games",
    "get_recent_games",
    "get_resumable_game",
    "get_scenario_totals",
    "init_db",
    "list_deep_analyses",
    "record_scenario_answers",
    "save_deep_analysis",
]
