"""AI opponents for Gin Rummy.

This module provides several AI implementations with varying strategies:

- BasicAI: Simple heuristic-based AI with configurable knock strategy
- ContextAwareAI: Extends BasicAI with game context awareness (opponent tracking,
  deck position, score pressure)
- StatisticalAI: Learns from experience by tracking action outcomes

All AIs share the BasicAI interface (context is optional everywhere):
- decide_draw(hand, discard_top, context=None) -> DrawChoice
- decide_discard(hand, context=None) -> Card
- should_knock(hand, context=None, pending_discard=None) -> bool
- make_turn_decision(hand, discard_top, drawn_card, context=None) -> (Card, bool)
- update_context / record_opponent_pickup / record_opponent_discard /
  reset_for_new_hand (no-ops on BasicAI, real tracking on the others)

Each decision method also has a `*_with_reasoning` variant that returns
detailed reasoning for debugging and UI display. Use `make_ai(name)` to
build one by name.
"""

from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.context_aware import ContextAwareAI
from gin_rummy.ai.factory import AI_TYPES, DIFFICULTY_TO_AI, make_ai
from gin_rummy.ai.monte_carlo import MonteCarloAI
from gin_rummy.ai.statistical import StatisticalAI
from gin_rummy.ai.types import (
    AIDecision,
    DiscardReasoning,
    DrawChoice,
    DrawReasoning,
    KnockReasoning,
    TurnReasoning,
)

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
    # Factory
    "AI_TYPES",
    "DIFFICULTY_TO_AI",
    "make_ai",
]
