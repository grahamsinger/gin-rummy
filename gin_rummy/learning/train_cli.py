"""gin-train: command-line front end for the Trainer."""

from __future__ import annotations

import logging
from pathlib import Path

from gin_rummy.learning.trainer import Trainer, TrainingConfig, TrainingMetrics

logger = logging.getLogger(__name__)


def main() -> None:
    """CLI entry point for training."""
    import argparse

    parser = argparse.ArgumentParser(description="Train LearningAI for Gin Rummy")
    parser.add_argument(
        "--episodes",
        type=int,
        default=10000,
        help="Total number of training episodes (when resuming, this includes episodes already completed)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/learning_ai.pt",
        help="Path to save trained model",
    )
    parser.add_argument(
        "--tensorboard",
        type=str,
        default="runs/gin_learning",
        help="TensorBoard log directory",
    )
    parser.add_argument(
        "--resume",
        type=str,
        help="Resume training from checkpoint",
    )
    parser.add_argument(
        "--eval-freq",
        type=int,
        default=500,
        help="Evaluate every N episodes",
    )
    parser.add_argument(
        "--save-freq",
        type=int,
        default=1000,
        help="Save checkpoint every N episodes",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed random, numpy and torch for a reproducible run",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging - suppress game logs unless verbose
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    else:
        # Only show trainer logs, suppress noisy game/AI logs
        logging.basicConfig(
            level=logging.WARNING,
            format="%(message)s",
        )
        # But keep trainer logger at INFO for important messages
        logging.getLogger("gin_rummy.learning.trainer").setLevel(logging.INFO)
        logging.getLogger(__name__).setLevel(logging.INFO)

    # Create config
    config = TrainingConfig(
        num_episodes=args.episodes,
        eval_freq=args.eval_freq,
        save_freq=args.save_freq,
        seed=args.seed,
    )

    # Create trainer
    save_path = Path(args.output)
    tensorboard_path = Path(args.tensorboard) if args.tensorboard else None

    trainer = Trainer(config, save_path, tensorboard_path)

    # Resume from checkpoint if specified
    if args.resume:
        resume_path = Path(args.resume)
        if resume_path.exists():
            logger.info("Resuming from checkpoint: %s", resume_path)
            trainer.load_checkpoint(resume_path)
        else:
            logger.warning("Checkpoint %s not found; starting from scratch", resume_path)

    # Progress bar state
    import sys
    import time

    start_time = time.time()
    last_rewards: list[float] = []

    def format_time(seconds: float) -> str:
        """Format seconds as HH:MM:SS or MM:SS."""
        if seconds < 3600:
            return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"
        return f"{int(seconds // 3600)}:{int((seconds % 3600) // 60):02d}:{int(seconds % 60):02d}"

    def progress_callback(metrics: TrainingMetrics) -> None:
        nonlocal last_rewards

        # Track recent rewards for averaging
        last_rewards.append(metrics.total_reward)
        if len(last_rewards) > 100:
            last_rewards = last_rewards[-100:]

        # Update progress bar every episode
        elapsed = time.time() - start_time
        progress = metrics.episode / config.num_episodes

        eta = elapsed / progress - elapsed if progress > 0 else 0

        avg_reward = sum(last_rewards) / len(last_rewards)

        # Build progress bar
        bar_width = 30
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)

        # Print progress line (overwrite previous)
        status = (
            f"\r[{bar}] {metrics.episode:>6}/{config.num_episodes} "
            f"| ε={metrics.exploration_rate:.3f} "
            f"| avg_r={avg_reward:>6.1f} "
            f"| buf={metrics.buffer_size:>6} "
            f"| {format_time(elapsed)}<{format_time(eta)}"
        )
        sys.stdout.write(status)
        sys.stdout.flush()

    # Run training
    print(f"Training {config.num_episodes} episodes on {trainer.device}...")
    trainer.train(callback=progress_callback)

    print(f"\n\nTraining complete! Model saved to {save_path}")


if __name__ == "__main__":
    main()
