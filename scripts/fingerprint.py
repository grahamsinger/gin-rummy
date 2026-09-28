#!/usr/bin/env python3
"""Behaviour fingerprint for refactors: seeded AI-vs-AI games, hashed per game.

Runs fixed-seed matchups and prints a hash of every game's final scores and
round count. A refactor that is meant to preserve behaviour must reproduce
the same hashes. Re-executes itself with PYTHONHASHSEED=0 so set iteration
order (Card hashes enum names, which are salted per process) cannot move the
result.

    uv run python scripts/fingerprint.py            # 150 games per matchup
    uv run python scripts/fingerprint.py -n 300 -s 7

The primary matchup (basic vs context) uses no `random` calls in the AIs, so
only the deck shuffle consumes the generator; a mismatch there is a real
behaviour change. The secondary matchup includes StatisticalAI, which shares
the global generator, so a mismatch there may only mean a random call moved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gin_rummy.ai import BasicAI, ContextAwareAI, StatisticalAI  # noqa: E402
from gin_rummy.config import Config  # noqa: E402
from gin_rummy.simulator import Simulator, SimulatorConfig  # noqa: E402

STATS = ROOT / "models" / "statistical_ai_backup.json"


def matchups() -> dict[str, tuple[BasicAI, BasicAI]]:
    cfg = Config()
    return {
        "primary   basic vs context     ": (BasicAI(cfg), ContextAwareAI(cfg)),
        "secondary context vs statistical": (ContextAwareAI(cfg), StatisticalAI(stats_path=str(STATS), config=cfg)),
    }


def fingerprint(ai1: BasicAI, ai2: BasicAI, games: int, seed: int) -> tuple[str, int, int]:
    sim = Simulator(ai1, ai2, SimulatorConfig(num_games=games, seed=seed))
    per_game: list[tuple[int, int, int]] = []
    original = sim._run_game

    def capture():
        result = original()
        per_game.append((result.score_p1, result.score_p2, result.rounds))
        return result

    sim._run_game = capture  # type: ignore[method-assign]
    metrics = sim.run()
    digest = hashlib.sha256(json.dumps(per_game).encode()).hexdigest()[:16]
    return digest, metrics.player1.games_won, metrics.player2.games_won


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("-n", "--games", type=int, default=150)
    parser.add_argument("-s", "--seed", type=int, default=42)
    args = parser.parse_args()

    for name, (ai1, ai2) in matchups().items():
        digest, w1, w2 = fingerprint(ai1, ai2, args.games, args.seed)
        print(f"{name}  games={args.games} seed={args.seed}  wins={w1}-{w2}  hash={digest}")


if __name__ == "__main__":
    main()
