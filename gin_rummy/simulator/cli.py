"""gin-simulate: command-line front end for the simulator."""

import argparse
import logging

from gin_rummy.ai import AI_TYPES, BasicAI, make_ai
from gin_rummy.config import Config
from gin_rummy.simulator.runner import Simulator, SimulatorConfig

logger = logging.getLogger(__name__)


def create_ai(
    ai_type: str,
    config_path: str | None,
    model_path: str | None = None,
    stats_path: str | None = None,
) -> BasicAI:
    """Create an AI with optional config override.

    Args:
        ai_type: Type of AI ("basic", "context", "learning", or "statistical").
        config_path: Optional path to config override file.
        model_path: Path to trained model (for "learning" type only).
        stats_path: Path to stats file (for "statistical" type only).

    Returns:
        BasicAI, ContextAwareAI, StatisticalAI, or LearningAI instance.
    """
    config = Config.with_overrides(config_path) if config_path else None
    return make_ai(ai_type, config, model_path=model_path, stats_path=stats_path)


def main() -> None:
    """CLI entry point for the simulator."""
    parser = argparse.ArgumentParser(
        description="Run AI vs AI Gin Rummy simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--num-games",
        type=int,
        default=100,
        help="Number of games to simulate",
    )
    parser.add_argument(
        "-t",
        "--target-score",
        type=int,
        default=100,
        help="Score needed to win a game (0 for single-round mode)",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=50,
        help="Maximum rounds per game (safety limit)",
    )
    parser.add_argument(
        "--ai1-type",
        type=str,
        choices=list(AI_TYPES),
        default="context",
        help="AI type for player 1",
    )
    parser.add_argument(
        "--ai2-type",
        type=str,
        choices=list(AI_TYPES),
        default="basic",
        help="AI type for player 2",
    )
    parser.add_argument(
        "--stats-file",
        type=str,
        default="models/statistical_ai.json",
        help="Path to stats file for Statistical AI (default: models/statistical_ai.json)",
    )
    parser.add_argument(
        "--ai1-config",
        type=str,
        default=None,
        help="Override config file for AI player 1",
    )
    parser.add_argument(
        "--ai2-config",
        type=str,
        default=None,
        help="Override config file for AI player 2",
    )
    parser.add_argument(
        "--ai1-model",
        type=str,
        default=None,
        help="Path to trained model for AI 1 (when --ai1-type=learning)",
    )
    parser.add_argument(
        "--ai2-model",
        type=str,
        default=None,
        help="Path to trained model for AI 2 (when --ai2-type=learning)",
    )

    args = parser.parse_args()

    # Configure logging based on verbosity
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose >= 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(name)s - %(levelname)s - %(message)s",
    )

    # Create AIs with optional config overrides
    ai1 = create_ai(args.ai1_type, args.ai1_config, args.ai1_model, args.stats_file)
    ai2 = create_ai(args.ai2_type, args.ai2_config, args.ai2_model, args.stats_file)

    config = SimulatorConfig(
        num_games=args.num_games,
        target_score=args.target_score,
        max_rounds_per_game=args.max_rounds,
        seed=args.seed,
    )

    # Show config info if overrides were used
    if args.ai1_config or args.ai2_config:
        print(f"AI 1: {args.ai1_type} (config: {args.ai1_config or 'default'})")
        print(f"AI 2: {args.ai2_type} (config: {args.ai2_config or 'default'})")
        print()

    simulator = Simulator(ai1=ai1, ai2=ai2, config=config)
    metrics = simulator.run(show_progress=True)

    # Save StatisticalAI stats after simulation
    for ai in [ai1, ai2]:
        if hasattr(ai, "save"):
            ai.save()
            if hasattr(ai, "get_stats_summary"):
                summary = ai.get_stats_summary()
                if summary.get("total_discard_samples", 0) > 0:
                    print(f"\nStatisticalAI stats: {summary['total_discard_samples']} samples collected")

    print(metrics.summary())


if __name__ == "__main__":
    main()
