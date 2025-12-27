"""Learning AI module for Gin Rummy using reinforcement learning.

This module provides a LearningAI that uses Deep Q-Learning with PyTorch
to learn optimal play through self-play and training.

Requires optional dependencies: uv sync --extra learning
"""

from __future__ import annotations

# Lazy imports to avoid requiring torch when not using learning features
__all__ = ["LearningAI", "StateEncoder", "Trainer"]


def __getattr__(name: str):
    """Lazy import to avoid loading torch until needed."""
    if name == "LearningAI":
        from gin_rummy.learning.learning_ai import LearningAI

        return LearningAI
    elif name == "StateEncoder":
        from gin_rummy.learning.state import StateEncoder

        return StateEncoder
    elif name == "Trainer":
        from gin_rummy.learning.trainer import Trainer

        return Trainer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
