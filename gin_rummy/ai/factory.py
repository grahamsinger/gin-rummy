"""Build an AI by name.

The single string-to-class mapping for the simulator, the trainer's
curriculum, the web UI's difficulty setting and the CLI.
"""

from __future__ import annotations

from concurrent.futures import Executor
from pathlib import Path
from typing import Any

from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.context_aware import ContextAwareAI
from gin_rummy.ai.monte_carlo import MonteCarloAI
from gin_rummy.ai.statistical import StatisticalAI
from gin_rummy.config import Config

AI_TYPES: tuple[str, ...] = ("basic", "context", "statistical", "montecarlo", "learning")

# Web UI difficulty names -> AI type
DIFFICULTY_TO_AI: dict[str, str] = {"easy": "basic", "medium": "context", "hard": "montecarlo"}


def make_ai(
    ai_type: str,
    config: Config | None = None,
    *,
    model_path: Path | str | None = None,
    stats_path: Path | str | None = None,
    pool: Executor | None = None,
    **kwargs: Any,
) -> BasicAI:
    """Create an AI instance.

    Args:
        ai_type: One of AI_TYPES.
        config: Optional config override (global config if None).
        model_path: Checkpoint for the "learning" type.
        stats_path: Statistics file for the "statistical" type.
        pool: Executor for the "montecarlo" type to run simulations on
            (borrowed, never shut down by the AI).
        **kwargs: Extra constructor arguments (e.g. exploration_rate, device
            for "learning").

    Raises:
        ValueError: For an unknown ai_type.
    """
    if ai_type == "basic":
        return BasicAI(config, **kwargs)
    if ai_type == "context":
        return ContextAwareAI(config, **kwargs)
    if ai_type == "montecarlo":
        return MonteCarloAI(config, pool=pool, **kwargs)
    if ai_type == "statistical":
        return StatisticalAI(stats_path=stats_path, config=config, **kwargs)
    if ai_type == "learning":
        # Lazy: torch is an optional dependency
        from gin_rummy.learning import LearningAI

        return LearningAI(model_path=model_path, config=config, **kwargs)
    raise ValueError(f"Unknown AI type {ai_type!r}; expected one of {', '.join(AI_TYPES)}")
