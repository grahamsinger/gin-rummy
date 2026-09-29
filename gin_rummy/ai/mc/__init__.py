"""Monte Carlo AI package.

- rollout: play a sampled position forward and score it
- sampling: partition unknown cards into an opponent hand and a deck
- workers: simulation batches (the unit of work sent to worker processes)
- ai: MonteCarloAI, the decision logic
"""

from gin_rummy.ai.mc.ai import MonteCarloAI
from gin_rummy.ai.mc.workers import worker_init

__all__ = ["MonteCarloAI", "worker_init"]
