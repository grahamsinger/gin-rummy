"""Scenario-quiz answers: every decision the player made and what each panel AI chose.

One row per (decision, AI), so agreement can be totalled per AI over all
time and the scoreboard survives server restarts.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from gin_rummy.db.connection import get_connection, init_db

DECISIONS = ("draw", "discard", "knock")


def record_scenario_answers(
    seed: int | None,
    decision: str,
    user_choice: str,
    ai_choices: list[tuple[str, str, bool]],
    db_path: Path | None = None,
) -> None:
    """Store one answered decision. `ai_choices` holds (ai_name, ai_choice, agrees) per panel AI."""
    init_db(db_path)
    answered_at = datetime.now().isoformat()
    with get_connection(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO scenario_answers
                (answered_at, seed, decision, user_choice, ai_name, ai_choice, agrees)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (answered_at, seed, decision, user_choice, name, choice, int(agrees))
                for name, choice, agrees in ai_choices
            ],
        )
        conn.commit()


def get_scenario_totals(db_path: Path | None = None) -> dict:
    """All-time agreement per AI, and how many scenarios have been answered.

    Returns {"scenarios": n, "by_ai": {name: {decision: {"agree": a, "total": t}}}}.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ai_name, decision, SUM(agrees) AS agree, COUNT(*) AS total
            FROM scenario_answers
            GROUP BY ai_name, decision
            """
        ).fetchall()
        # Every scenario starts with exactly one draw decision
        scenarios = conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT answered_at, seed FROM scenario_answers WHERE decision = 'draw')"
        ).fetchone()[0]

    by_ai: dict[str, dict[str, dict[str, int]]] = {}
    for row in rows:
        per_ai = by_ai.setdefault(row["ai_name"], {d: {"agree": 0, "total": 0} for d in DECISIONS})
        per_ai[row["decision"]] = {"agree": row["agree"], "total": row["total"]}
    return {"scenarios": scenarios, "by_ai": by_ai}
