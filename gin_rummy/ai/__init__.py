"""AI opponents for Gin Rummy.

This module provides several AI implementations with varying strategies:

- BasicAI: Simple heuristic-based AI with configurable knock strategy
- ContextAwareAI: Extends BasicAI with game context awareness (opponent tracking,
  deck position, score pressure)
- StatisticalAI: Learns from experience by tracking action outcomes

All AIs share a common interface:
- decide_draw(hand, discard_top) -> DrawChoice
- decide_discard(hand) -> Card
- should_knock(hand) -> bool
- make_turn_decision(hand, discard_top, drawn_card) -> (Card, bool)

Each method also has a `*_with_reasoning` variant that returns detailed
decision reasoning for debugging and UI display.
"""

from gin_rummy.ai.types import (
    DrawChoice,
    AIDecision,
    DrawReasoning,
    DiscardReasoning,
    KnockReasoning,
    TurnReasoning,
)
from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.context_aware import ContextAwareAI
from gin_rummy.ai.statistical import StatisticalAI
from gin_rummy.ai.monte_carlo import MonteCarloAI

__all__ = [
    # Types
    "DrawChoice",
    "AIDecision",
    "DrawReasoning",
    "DiscardReasoning",
    "KnockReasoning",
    "TurnReasoning",
    # AI classes
    "BasicAI",
    "ContextAwareAI",
    "StatisticalAI",
    "MonteCarloAI",
]
