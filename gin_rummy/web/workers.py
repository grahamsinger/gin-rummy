"""One process pool shared by every Monte Carlo AI in the web app.

Each MonteCarloAI used to start its own ProcessPoolExecutor (cpu_count-1
processes) and relied on __del__ to stop it. The web app now lends every
"hard" AI and every scenario panel this single pool, which caps the total
worker count and avoids restarting processes each hand. The app lifespan
shuts it down on exit.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ProcessPoolExecutor

from gin_rummy.ai.mc import worker_init
from gin_rummy.config import get_config

_pool: ProcessPoolExecutor | None = None
_lock = threading.Lock()


def worker_count() -> int:
    """Pool size from config (max_workers, or cpu_count-1 when 0)."""
    configured = get_config().monte_carlo_ai.max_workers
    return max(1, (os.cpu_count() or 2) - 1) if configured == 0 else max(1, configured)


def get_worker_pool() -> ProcessPoolExecutor | None:
    """The shared pool, created on first use. None means run simulations inline."""
    global _pool
    workers = worker_count()
    if workers <= 1:
        return None
    with _lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(max_workers=workers, initializer=worker_init)
        return _pool


def shutdown_worker_pool(wait: bool = True) -> None:
    """Stop the shared pool (app shutdown, tests)."""
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=wait)
