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
- monte_carlo: a sequential MonteCarloAI (one worker, 40 simulations) on
  the same positions: its choices plus the expected-value numbers behind
  them, so a change in sampling or rollout order shows up. Worker pools
  reseed per process and are not reproducible, hence one worker.
- learning: a short seeded training run with exploration off (episode
  rewards, evaluation and a checksum of the trained weights), and the
  greedy choices of a seeded, untrained LearningAI on the scenario
  positions. Both are float-sensitive, so compare them only on the same
  machine and torch build. Skipped when torch is not installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from dataclasses import replace
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gin_rummy.ai import BasicAI, ContextAwareAI, MonteCarloAI, StatisticalAI  # noqa: E402
from gin_rummy.config import Config  # noqa: E402
from gin_rummy.game import Game  # noqa: E402
from gin_rummy.models import Hand  # noqa: E402
from gin_rummy.scenario_quiz import HUMAN_SEAT, PanelMember, describe_position, generate_stable_scenario  # noqa: E402
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


Position = tuple[Game | None, dict | None]


def scenario_positions(count: int, seed: int) -> list[Position]:
    """The positions the scenario quiz generates for `count` consecutive seeds, with their descriptions.

    The panel is the two cheap deterministic advisors; MonteCarloAI is left
    out because the panel is only fed during generation, never asked.
    """
    cfg = Config()
    panel = [PanelMember("BasicAI", BasicAI(cfg)), PanelMember("ContextAwareAI", ContextAwareAI(cfg))]
    positions: list[Position] = []
    for i in range(count):
        game = generate_stable_scenario(seed + i, panel)
        positions.append((game, None if game is None else describe_position(game, panel)))
    return positions


def scenario_fingerprint(positions: list[Position]) -> tuple[str, int]:
    """Hash the described positions."""
    described = [d for _, d in positions]
    return _digest(described), sum(d is not None for d in described)


def monte_carlo_fingerprint(positions: list[Position], seed: int, sims: int = 40) -> str:
    """Hash a sequential MonteCarloAI's decisions and expected values on each position."""
    cfg = Config()
    mc = replace(
        cfg.monte_carlo_ai, draw_simulations=sims, discard_simulations=sims, knock_simulations=sims, max_workers=1
    )
    ai = MonteCarloAI(replace(cfg, monte_carlo_ai=mc))
    rows = []
    for i, (game, _) in enumerate(positions):
        if game is None:
            rows.append(None)
            continue
        random.seed(seed + i)
        ai.reset_for_new_hand()
        ctx = game.get_game_context(HUMAN_SEAT)
        hand = game.players[HUMAN_SEAT].hand
        top = game.top_of_discard
        assert top is not None
        draw = ai.decide_draw(hand, top, ctx)
        hand11 = Hand([*hand, top])
        ctx = replace(ctx, drawn_card=top)
        discard = ai.decide_discard(hand11, ctx)
        post = Hand([c for c in hand11 if c != discard])
        can_knock = post.deadwood_total <= ctx.knock_threshold
        knock = ai.should_knock(post, ctx, pending_discard=discard) if can_knock else None
        thinking = ai.last_mc_thinking or {}
        d, c, k = thinking.get("draw") or {}, thinking.get("discard") or {}, thinking.get("knock") or {}
        rows.append(
            {
                "draw": (draw.name, d.get("deck_avg_points"), d.get("discard_avg_points")),
                "discard": (discard.code, [(x["card"], x["avg_points"]) for x in c.get("candidates", [])]),
                "knock": (knock, k.get("knock_avg_points"), k.get("continue_avg_points"), k.get("reason")),
            }
        )
    ai.shutdown()
    return _digest(rows)


def learning_greedy_fingerprint(positions: list[Position], seed: int) -> str | None:
    """Hash a seeded, untrained LearningAI's greedy draw/discard/knock on each position.

    This exercises the decision path (state encoding, networks, context
    handling) directly, which the short training run barely does.
    """
    try:
        import torch
    except ImportError:
        return None
    from gin_rummy.learning.learning_ai import LearningAI

    torch.manual_seed(seed)
    ai = LearningAI(config=Config(), exploration_rate=0.0, device="cpu")
    ai.eval_mode()
    choices = []
    for game, _ in positions:
        if game is None:
            choices.append(None)
            continue
        ai.reset_for_new_hand()
        ctx = game.get_game_context(HUMAN_SEAT)
        hand = game.players[HUMAN_SEAT].hand
        top = game.top_of_discard
        assert top is not None
        draw = ai.decide_draw(hand, top, ctx)
        hand11 = Hand([*hand, top])
        ctx = replace(ctx, drawn_card=top)  # as the runner's post-draw context would say
        discard = ai.decide_discard(hand11, ctx)
        post = Hand([c for c in hand11 if c != discard])
        can_knock = post.deadwood_total <= ctx.knock_threshold
        knock = ai.should_knock(post, ctx, pending_discard=discard) if can_knock else None
        choices.append((draw.name, discard.code, knock))
    return _digest(choices)


def learning_fingerprint(seed: int) -> tuple[str, int] | None:
    """Hash a short seeded training run (exploration off), or None when torch is not installed."""
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
        exploration_start=0.0,
        exploration_end=0.0,
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

    positions = scenario_positions(args.scenarios, args.seed)
    digest, generated = scenario_fingerprint(positions)
    print(
        f"scenario  quiz positions        seeds={args.scenarios} seed={args.seed}  generated={generated}  hash={digest}"
    )

    digest = monte_carlo_fingerprint(positions, args.seed)
    print(f"monte_carlo sequential decisions  seeds={args.scenarios} seed={args.seed} sims=40  hash={digest}")

    if not args.no_learning:
        result = learning_fingerprint(args.seed)
        if result is None:
            print("learning  (torch not installed, skipped)")
        else:
            digest, buffer_size = result
            print(f"learning  seeded training run   episodes=4 seed={args.seed}  buffer={buffer_size}  hash={digest}")
            greedy = learning_greedy_fingerprint(positions, args.seed)
            print(f"learning  greedy on positions   seeds={args.scenarios} seed={args.seed}  hash={greedy}")


if __name__ == "__main__":
    main()
