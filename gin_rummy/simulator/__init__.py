"""AI vs AI game simulator with metrics collection.

- metrics: GameResult, PlayerMetrics, SimulatorMetrics
- runner: SimulatorConfig, Simulator, run_simulation
- cli: create_ai and main (the gin-simulate entry point)
"""

from gin_rummy.simulator.cli import create_ai, main
from gin_rummy.simulator.metrics import GameResult, PlayerMetrics, SimulatorMetrics
from gin_rummy.simulator.runner import Simulator, SimulatorConfig, run_simulation

__all__ = [
    "GameResult",
    "PlayerMetrics",
    "Simulator",
    "SimulatorConfig",
    "SimulatorMetrics",
    "create_ai",
    "main",
    "run_simulation",
]
