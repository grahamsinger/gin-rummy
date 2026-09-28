"""Monte Carlo worker-pool lifecycle in the web app (AUDIT "Next up" A).

The regression the audit measured: replacing the AI or expiring a session
must not change the number of worker processes, and app shutdown must
stop them all.
"""

from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import pytest

import gin_rummy.config as config_module
import gin_rummy.web.workers as workers
from gin_rummy.ai import MonteCarloAI
from gin_rummy.config import Config
from gin_rummy.web.session_store import SessionStore
from tests.helpers import make_mc_config


def _workers_alive() -> int:
    return len(mp.active_children())


@pytest.fixture
def small_pool_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    cfg = make_mc_config(max_workers=2, draw_simulations=4, discard_simulations=4, knock_simulations=4)
    cfg.display = replace(cfg.display, clear_screen=False, ai_turn_delay=0.0)
    monkeypatch.setattr(config_module, "_config", cfg)
    workers.shutdown_worker_pool()
    yield cfg
    workers.shutdown_worker_pool()


class TestBorrowedPool:
    def test_ai_never_shuts_down_a_borrowed_pool(self):
        pool = ProcessPoolExecutor(max_workers=1)
        try:
            ai = MonteCarloAI(make_mc_config(max_workers=4), pool=pool)
            assert ai._get_pool() is pool
            ai.shutdown()
            assert pool.submit(abs, -1).result() == 1  # still usable
        finally:
            pool.shutdown(wait=True)

    def test_ai_owns_and_shuts_down_its_own_pool(self):
        ai = MonteCarloAI(make_mc_config(max_workers=2))
        pool = ai._get_pool()
        assert pool is not None and ai._owns_pool
        ai.shutdown()
        assert ai._pool is None
        with pytest.raises(RuntimeError):
            pool.submit(abs, -1)


class TestSessionLifecycle:
    def test_process_count_is_stable_across_hands_and_eviction(self, small_pool_config, isolated_db):
        store = SessionStore(ttl_seconds=3600)
        sid, session = store.create_session()
        session.new_game(player_name="T", ai_difficulty="hard")
        ai = session.ai
        assert isinstance(ai, MonteCarloAI)

        shared = workers.get_worker_pool()
        assert shared is not None and ai._get_pool() is shared and not ai._owns_pool
        shared.submit(abs, -1).result()  # make sure at least one worker is up
        alive = _workers_alive()
        assert alive >= 1

        # New hands reuse the same AI and start no processes
        session.game.phase = session.game.phase.__class__.ROUND_OVER
        for _ in range(3):
            session.game.phase = session.game.phase.__class__.ROUND_OVER
            session.new_round()
            assert session.ai is ai
            assert _workers_alive() == alive

        # A second "hard" session shares the pool too
        _, other = store.create_session()
        other.new_game(player_name="U", ai_difficulty="hard")
        assert other.ai._get_pool() is shared
        assert _workers_alive() == alive

        # Eviction closes the session explicitly, without touching the shared pool
        store._sessions[sid].last_accessed = -1e12
        assert store.cleanup_expired() == 1
        assert session.closed
        assert _workers_alive() == alive

        # App shutdown closes the rest and stops every worker
        assert store.close_all() == 1
        workers.shutdown_worker_pool(wait=True)
        assert _workers_alive() == 0
