"""Experiment runner for hyperparameter tuning.

Allows easy A/B testing of different training configurations via CLI.

Usage:
    uv run gin-experiment --lr 0.0003 --batch-size 128 --episodes 5000
    uv run gin-experiment --preset fast
    uv run gin-experiment --preset thorough
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from gin_rummy.learning.rewards import RewardConfig
from gin_rummy.learning.trainer import Trainer, TrainingConfig, TrainingMetrics


# Preset configurations for common experiments
PRESETS = {
    "fast": {
        "description": "Quick test run (1000 episodes)",
        "num_episodes": 1000,
        "eval_freq": 200,
        "save_freq": 500,
    },
    "standard": {
        "description": "Standard training (10000 episodes)",
        "num_episodes": 10000,
        "eval_freq": 500,
        "save_freq": 1000,
    },
    "thorough": {
        "description": "Thorough training (25000 episodes)",
        "num_episodes": 25000,
        "eval_freq": 1000,
        "save_freq": 2500,
    },
    "low-lr": {
        "description": "Lower learning rate for stability",
        "num_episodes": 10000,
        "learning_rate": 0.0003,
    },
    "big-batch": {
        "description": "Larger batch size",
        "num_episodes": 10000,
        "batch_size": 128,
    },
    "slow-explore": {
        "description": "Slower exploration decay",
        "num_episodes": 15000,
        "exploration_decay": 0.9998,
    },
    "aggressive-rewards": {
        "description": "Higher reward signals",
        "num_episodes": 10000,
        "reward_config": {
            "win_by_gin": 75.0,
            "win_by_knock": 30.0,
            "deadwood_reduction_bonus": 0.2,
            "meld_completion_bonus": 2.0,
        },
    },
}


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with all hyperparameters."""
    parser = argparse.ArgumentParser(
        description="Run training experiments with custom hyperparameters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test
  uv run gin-experiment --preset fast

  # Custom learning rate
  uv run gin-experiment --lr 0.0003 --episodes 10000

  # Multiple tweaks
  uv run gin-experiment --lr 0.0005 --batch-size 128 --gamma 0.95

  # List available presets
  uv run gin-experiment --list-presets
        """,
    )

    # Presets
    parser.add_argument(
        "--preset",
        type=str,
        choices=list(PRESETS.keys()),
        help="Use a preset configuration",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets and exit",
    )

    # Training duration
    parser.add_argument(
        "--episodes", "-n",
        type=int,
        help="Number of training episodes (default: 10000)",
    )

    # Network training params
    parser.add_argument(
        "--lr", "--learning-rate",
        type=float,
        dest="learning_rate",
        help="Learning rate (default: 0.001)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Batch size (default: 64)",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        help="Discount factor (default: 0.99)",
    )

    # Exploration params
    parser.add_argument(
        "--exploration-start",
        type=float,
        help="Starting exploration rate (default: 1.0)",
    )
    parser.add_argument(
        "--exploration-end",
        type=float,
        help="Final exploration rate (default: 0.05)",
    )
    parser.add_argument(
        "--exploration-decay",
        type=float,
        help="Exploration decay rate (default: 0.9995)",
    )

    # Target network
    parser.add_argument(
        "--target-update-freq",
        type=int,
        help="Episodes between target network updates (default: 100)",
    )

    # Buffer
    parser.add_argument(
        "--buffer-capacity",
        type=int,
        help="Replay buffer capacity (default: 100000)",
    )
    parser.add_argument(
        "--min-buffer-size",
        type=int,
        help="Min experiences before training (default: 1000)",
    )

    # Reward shaping
    parser.add_argument(
        "--win-gin-reward",
        type=float,
        help="Reward for winning with gin (default: 50.0)",
    )
    parser.add_argument(
        "--win-knock-reward",
        type=float,
        help="Reward for winning by knock (default: 20.0)",
    )
    parser.add_argument(
        "--deadwood-bonus",
        type=float,
        help="Bonus per deadwood point reduced (default: 0.1)",
    )
    parser.add_argument(
        "--meld-bonus",
        type=float,
        help="Bonus for completing a meld (default: 1.0)",
    )

    # Evaluation
    parser.add_argument(
        "--eval-freq",
        type=int,
        help="Evaluate every N episodes (default: 500)",
    )
    parser.add_argument(
        "--save-freq",
        type=int,
        help="Save checkpoint every N episodes (default: 1000)",
    )

    # Output
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output model path (default: auto-generated)",
    )
    parser.add_argument(
        "--name",
        type=str,
        help="Experiment name (used in output path)",
    )
    parser.add_argument(
        "--no-tensorboard",
        action="store_true",
        help="Disable TensorBoard logging",
    )

    # Verbosity
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


def build_config(args: argparse.Namespace) -> tuple[TrainingConfig, str]:
    """Build TrainingConfig from parsed arguments.

    Returns:
        Tuple of (config, experiment_name)
    """
    # Start with defaults
    config_kwargs = {}
    reward_kwargs = {}

    # Apply preset if specified
    if args.preset:
        preset = PRESETS[args.preset]
        for key, value in preset.items():
            if key == "description":
                continue
            elif key == "reward_config":
                reward_kwargs.update(value)
            else:
                config_kwargs[key] = value

    # Override with explicit arguments
    arg_mapping = {
        "episodes": "num_episodes",
        "learning_rate": "learning_rate",
        "batch_size": "batch_size",
        "gamma": "gamma",
        "exploration_start": "exploration_start",
        "exploration_end": "exploration_end",
        "exploration_decay": "exploration_decay",
        "target_update_freq": "target_update_freq",
        "buffer_capacity": "buffer_capacity",
        "min_buffer_size": "min_buffer_size",
        "eval_freq": "eval_freq",
        "save_freq": "save_freq",
    }

    for arg_name, config_name in arg_mapping.items():
        value = getattr(args, arg_name.replace("-", "_"), None)
        if value is not None:
            config_kwargs[config_name] = value

    # Reward config overrides
    reward_mapping = {
        "win_gin_reward": "win_by_gin",
        "win_knock_reward": "win_by_knock",
        "deadwood_bonus": "deadwood_reduction_bonus",
        "meld_bonus": "meld_completion_bonus",
    }

    for arg_name, reward_name in reward_mapping.items():
        value = getattr(args, arg_name.replace("-", "_"), None)
        if value is not None:
            reward_kwargs[reward_name] = value

    # Create reward config if any rewards were customized
    if reward_kwargs:
        config_kwargs["reward_config"] = RewardConfig(**reward_kwargs)

    # Generate experiment name
    if args.name:
        exp_name = args.name
    elif args.preset:
        exp_name = f"{args.preset}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    else:
        # Generate from key params
        parts = []
        if "learning_rate" in config_kwargs:
            parts.append(f"lr{config_kwargs['learning_rate']}")
        if "batch_size" in config_kwargs:
            parts.append(f"bs{config_kwargs['batch_size']}")
        if "gamma" in config_kwargs:
            parts.append(f"g{config_kwargs['gamma']}")
        if "exploration_decay" in config_kwargs:
            parts.append(f"ed{config_kwargs['exploration_decay']}")
        if not parts:
            parts.append("default")
        parts.append(datetime.now().strftime("%H%M%S"))
        exp_name = "_".join(parts)

    return TrainingConfig(**config_kwargs), exp_name


def main() -> None:
    """Run experiment."""
    parser = create_parser()
    args = parser.parse_args()

    # List presets
    if args.list_presets:
        print("\nAvailable presets:\n")
        for name, preset in PRESETS.items():
            desc = preset.get("description", "No description")
            print(f"  {name:20s} - {desc}")
            for key, value in preset.items():
                if key != "description":
                    print(f"                         {key}: {value}")
            print()
        return

    # Build config
    config, exp_name = build_config(args)

    # Setup paths
    if args.output:
        save_path = Path(args.output)
    else:
        save_path = Path(f"models/experiments/{exp_name}.pt")

    tensorboard_path = None if args.no_tensorboard else Path(f"runs/{exp_name}")

    # Setup logging
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        logging.getLogger("gin_rummy.learning.trainer").setLevel(logging.INFO)

    # Print experiment info
    print(f"\n{'='*60}")
    print(f"Experiment: {exp_name}")
    print(f"{'='*60}")
    print(f"\nTraining Config:")
    print(f"  episodes:          {config.num_episodes}")
    print(f"  learning_rate:     {config.learning_rate}")
    print(f"  batch_size:        {config.batch_size}")
    print(f"  gamma:             {config.gamma}")
    print(f"  exploration_decay: {config.exploration_decay}")
    print(f"  target_update:     {config.target_update_freq}")
    print(f"\nReward Config:")
    print(f"  win_by_gin:        {config.reward_config.win_by_gin}")
    print(f"  win_by_knock:      {config.reward_config.win_by_knock}")
    print(f"  deadwood_bonus:    {config.reward_config.deadwood_reduction_bonus}")
    print(f"  meld_bonus:        {config.reward_config.meld_completion_bonus}")
    print(f"\nOutput: {save_path}")
    if tensorboard_path:
        print(f"TensorBoard: {tensorboard_path}")
    print(f"{'='*60}\n")

    # Save config for reproducibility
    save_path.parent.mkdir(parents=True, exist_ok=True)
    config_path = save_path.with_suffix(".json")
    with open(config_path, "w") as f:
        config_dict = {
            "training": {k: v for k, v in asdict(config).items() if k != "reward_config"},
            "rewards": asdict(config.reward_config),
            "experiment_name": exp_name,
            "timestamp": datetime.now().isoformat(),
        }
        # Handle non-serializable curriculum
        config_dict["training"]["curriculum"] = [
            {"opponent": opp, "episodes": eps}
            for opp, eps in config.curriculum
        ]
        json.dump(config_dict, f, indent=2)
    print(f"Config saved to {config_path}\n")

    # Create trainer
    trainer = Trainer(config, save_path, tensorboard_path)

    # Progress tracking
    start_time = time.time()
    last_rewards: list[float] = []
    best_avg_points = float("-inf")

    def format_time(seconds: float) -> str:
        if seconds < 3600:
            return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"
        return f"{int(seconds // 3600)}:{int((seconds % 3600) // 60):02d}:{int(seconds % 60):02d}"

    def progress_callback(metrics: TrainingMetrics) -> None:
        nonlocal last_rewards, best_avg_points

        last_rewards.append(metrics.total_reward)
        if len(last_rewards) > 100:
            last_rewards = last_rewards[-100:]

        elapsed = time.time() - start_time
        progress = metrics.episode / config.num_episodes
        eta = (elapsed / progress - elapsed) if progress > 0 else 0
        avg_reward = sum(last_rewards) / len(last_rewards)

        # Track best
        if metrics.avg_points_per_game > best_avg_points and metrics.avg_points_per_game > 0:
            best_avg_points = metrics.avg_points_per_game

        bar_width = 30
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)

        status = (
            f"\r[{bar}] {metrics.episode:>6}/{config.num_episodes} "
            f"| ε={metrics.exploration_rate:.3f} "
            f"| avg_r={avg_reward:>6.1f} "
            f"| buf={metrics.buffer_size:>6} "
            f"| {format_time(elapsed)}<{format_time(eta)}"
        )

        # Show eval results when available
        if metrics.win_rate > 0 or metrics.avg_points_per_game != 0:
            status += f" | eval: {metrics.win_rate:.0%} win, {metrics.avg_points_per_game:.1f} pts"

        sys.stdout.write(status)
        sys.stdout.flush()

    # Run training
    print(f"Training on {trainer.device}...\n")
    trainer.train(callback=progress_callback)

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"Training Complete!")
    print(f"{'='*60}")
    print(f"  Duration:       {format_time(elapsed)}")
    print(f"  Model saved:    {save_path}")
    print(f"  Config saved:   {config_path}")
    print(f"  Best avg_pts:   {best_avg_points:.1f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
