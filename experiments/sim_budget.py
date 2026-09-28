"""Experiment: how does simulation budget affect MC AI win rate?

Tests Low (20), Default (100), and High (500) simulations per decision
against BasicAI, all on the same seed.
"""

import sys
import time

from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.monte_carlo import MonteCarloAI
from gin_rummy.config import Config, MonteCarloAIConfig
from gin_rummy.simulator import Simulator, SimulatorConfig

SEED = 42
NUM_GAMES = 50

CONFIGS = {
    "Low (20)": MonteCarloAIConfig(
        draw_simulations=20,
        discard_simulations=20,
        knock_simulations=20,
        max_workers=0,
        sample_strategy="paired",
    ),
    "Default (100)": MonteCarloAIConfig(
        draw_simulations=100,
        discard_simulations=100,
        knock_simulations=100,
        max_workers=0,
        sample_strategy="paired",
    ),
    "High (500)": MonteCarloAIConfig(
        draw_simulations=500,
        discard_simulations=500,
        knock_simulations=500,
        max_workers=0,
        sample_strategy="paired",
    ),
}


def run_experiment(label: str, mc_config: MonteCarloAIConfig) -> dict:
    config = Config()
    config.monte_carlo_ai = mc_config
    ai1 = MonteCarloAI(config=config)
    ai2 = BasicAI()

    sim_config = SimulatorConfig(
        num_games=NUM_GAMES,
        seed=SEED,
    )
    sim = Simulator(ai1=ai1, ai2=ai2, config=sim_config)

    sys.stderr.write(f"\nRunning: {label} ({NUM_GAMES} games)...\n")
    sys.stderr.flush()

    start = time.time()
    metrics = sim.run(show_progress=True)
    elapsed = time.time() - start

    ai1.shutdown()

    p1 = metrics.player1
    p2 = metrics.player2

    return {
        "label": label,
        "wins": p1.games_won,
        "losses": p2.games_won,
        "win_pct": p1.games_won / max(1, metrics.games_played) * 100,
        "rounds_won": p1.rounds_won,
        "rounds_lost": p2.rounds_won,
        "total_points": p1.total_points,
        "opp_points": p2.total_points,
        "gins": p1.gins,
        "avg_knock_dw": p1.total_knock_deadwood / max(1, p1.knocks),
        "elapsed": elapsed,
    }


def main():
    results = []
    for label, mc_config in CONFIGS.items():
        result = run_experiment(label, mc_config)
        results.append(result)

    # Print comparison table
    print("\n" + "=" * 80)
    print("SIMULATION BUDGET EXPERIMENT")
    print(f"MC AI (Player 1) vs BasicAI (Player 2) — {NUM_GAMES} games, seed={SEED}")
    print("=" * 80)

    header = (
        f"{'Config':<20} {'Wins':>5} {'Losses':>6} {'Win%':>6} {'Rnds W':>6} {'Rnds L':>6} "
        f"{'Pts':>6} {'Opp Pts':>7} {'Gins':>4} {'AvgKnDW':>7} {'Time':>7}"
    )
    print(header)
    print("-" * len(header))

    for r in results:
        print(
            f"{r['label']:<20} "
            f"{r['wins']:>5} "
            f"{r['losses']:>6} "
            f"{r['win_pct']:>5.1f}% "
            f"{r['rounds_won']:>6} "
            f"{r['rounds_lost']:>6} "
            f"{r['total_points']:>6} "
            f"{r['opp_points']:>7} "
            f"{r['gins']:>4} "
            f"{r['avg_knock_dw']:>7.1f} "
            f"{r['elapsed']:>6.0f}s"
        )

    print("=" * 80)


if __name__ == "__main__":
    main()
