"""Monte Carlo AI package.

- rollout: play a sampled position forward and score it
- sampling: partition unknown cards into an opponent hand and a deck
- workers: simulation batches (the unit of work sent to worker processes)
- thinking: typed per-decision data (what the AI was thinking) and its display text
- ai: MonteCarloAI, the decision logic
"""

from gin_rummy.ai.mc.ai import MonteCarloAI
from gin_rummy.ai.mc.thinking import DiscardCandidate, MCThinking
from gin_rummy.ai.mc.workers import worker_init

__all__ = ["DiscardCandidate", "MCThinking", "MonteCarloAI", "worker_init"]
