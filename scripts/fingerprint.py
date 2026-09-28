#!/usr/bin/env python3
"""Behaviour fingerprint for refactors: seeded AI-vs-AI games, hashed per game.

Runs fixed-seed matchups and prints a hash of every game's final scores and
round count. A refactor that is meant to preserve behaviour must reproduce
the same hashes. Re-executes itself with PYTHONHASHSEED=0 so set iteration
order (Card hashes enum names, which are salted per process) cannot move the
result.

    uv run python scripts/fingerprint.py            # 150 games per matchup
    uv run python scripts/fingerprint.py -n 300 -s 7
    uv run python scripts/fingerprint.py --no-learning   # skip the training run

The primary matchup (basic vs context) uses no `random` calls in the AIs, so
only the deck shuffle consumes the generator; a mismatch there is a real
behaviour change. The secondary matchup includes StatisticalAI, which shares
the global generator, so a mismatch there may only mean a random call moved.

Two more lines cover the other loop-style callers:
- scenario: the frozen positions the scenario quiz generates (20 seeds) plus
  the panel's draw advice, so opponent tracking fed by callbacks is included.
- learning: a short seeded training run (episode rewards, evaluation and a
  checksum of the trained weights). Float-sensitive, so compare it only on
  the same machine and torch build. Skipped when torch is not installed.
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
from gin_rummy.scenario_quiz import PanelMember, describe_position, generate_stable_scenario  # noqa: E402
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


def _digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def scenario_fingerprint(count: int, seed: int) -> tuple[str, int]:
    """Hash the positions the scenario quiz generates for `count` consecutive seeds.

    The panel is the two cheap deterministic advisors; MonteCarloAI is left
    out because the panel is only fed during generation, never asked.
    """
    cfg = Config()
    panel = [PanelMember("BasicAI", BasicAI(cfg)), PanelMember("ContextAwareAI", ContextAwareAI(cfg))]
    positions = []
    for i in range(count):
        game = generate_stable_scenario(seed + i, panel)
        positions.append(None if game is None else describe_position(game, panel))
    return _digest(positions), sum(p is not None for p in positions)


def learning_fingerprint(seed: int) -> tuple[str, int] | None:
    """Hash a short seeded training run, or None when torch is not installed."""
    try:
        import torch
    except ImportError:
        return None
    import tempfile

    from gin_rummy.learning.trainer import Trainer, TrainingConfig

    config = TrainingConfig(
        num_episodes=4,
        target_score=30,
        max_rounds_per_game=6,
        batch_size=16,
        min_buffer_size=40,
        eval_freq=2,
        eval_games=2,
        save_freq=10_000,
        curriculum=[("basic", 2), ("context", 2)],
        seed=seed,
    )
    with tempfile.TemporaryDirectory() as tmp:
        trainer = Trainer(config, Path(tmp) / "fp.pt")
        trainer.train()
        rows = [
            (m.episode, round(m.total_reward, 6), m.buffer_size, round(m.win_rate, 6), round(m.avg_points_per_game, 6))
            for m in trainer.metrics_history
        ]
        checksum = 0.0
        with torch.no_grad():
            for net in (trainer.learning_ai.draw_net, trainer.learning_ai.discard_net, trainer.learning_ai.knock_net):
                checksum += sum(float(p.abs().sum()) for p in net.parameters())
    return _digest([rows, round(checksum, 4)]), len(trainer.replay_buffer)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("-n", "--games", type=int, default=150)
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("--scenarios", type=int, default=20, help="seeds for the scenario line")
    parser.add_argument("--no-learning", action="store_true", help="skip the seeded training run")
    args = parser.parse_args()

    for name, (ai1, ai2) in matchups().items():
        digest, w1, w2 = fingerprint(ai1, ai2, args.games, args.seed)
        print(f"{name}  games={args.games} seed={args.seed}  wins={w1}-{w2}  hash={digest}")

    digest, generated = scenario_fingerprint(args.scenarios, args.seed)
    print(
        f"scenario  quiz positions        seeds={args.scenarios} seed={args.seed}  generated={generated}  hash={digest}"
    )

    if not args.no_learning:
        result = learning_fingerprint(args.seed)
        if result is None:
            print("learning  (torch not installed, skipped)")
        else:
            digest, buffer_size = result
            print(f"learning  seeded training run   episodes=4 seed={args.seed}  buffer={buffer_size}  hash={digest}")


if __name__ == "__main__":
    main()
