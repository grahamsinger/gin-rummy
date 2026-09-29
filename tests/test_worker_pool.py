"""Monte Carlo worker-pool lifecycle in the web app (AUDIT "Next up" A).

The regression the audit measured: replacing the AI or expiring a session
must not change the number of worker processes, and app shutdown must
stop them all.
"""

from __future__ import annotations

import multiprocessing as mp
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import pytest

import gin_rummy.config as config_module
import gin_rummy.web.workers as workers
from gin_rummy.ai import DrawChoice, MonteCarloAI
from gin_rummy.ai.mc import MCThinking
from gin_rummy.config import Config
from gin_rummy.models import Card, Hand
from gin_rummy.web.session_store import SessionStore
from tests.helpers import make_mc_config


def _workers_alive() -> int:
    return len(mp.active_children())


def _negate(x: int) -> int:
    """Picklable job for probing a pool."""
    return -x


@pytest.fixture
def small_pool_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
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
            assert pool.submit(_negate, -1).result() == 1  # still usable
        finally:
            pool.shutdown(wait=True)

    def test_ai_owns_and_shuts_down_its_own_pool(self):
        ai = MonteCarloAI(make_mc_config(max_workers=2))
        pool = ai._get_pool()
        assert pool is not None and ai._owns_pool
        ai.shutdown()
        assert ai._pool is None
        with pytest.raises(RuntimeError):
            pool.submit(_negate, -1)


class TestSessionLifecycle:
    def test_process_count_is_stable_across_hands_and_eviction(self, small_pool_config, isolated_db):
        store = SessionStore(ttl_seconds=3600)
        sid, session = store.create_session()
        session.new_game(player_name="T", ai_difficulty="hard")
        ai = session.ai
        game = session.game
        assert isinstance(ai, MonteCarloAI) and game is not None

        shared = workers.get_worker_pool()
        assert shared is not None and ai._get_pool() is shared and not ai._owns_pool
        shared.submit(_negate, -1).result()  # make sure at least one worker is up
        alive = _workers_alive()
        assert alive >= 1

        # New hands reuse the same AI and start no processes
        for _ in range(3):
            game.phase = game.phase.__class__.ROUND_OVER
            session.new_round()
            assert session.ai is ai
            assert _workers_alive() == alive

        # A second "hard" session shares the pool too
        _, other = store.create_session()
        other.new_game(player_name="U", ai_difficulty="hard")
        assert isinstance(other.ai, MonteCarloAI) and other.ai._get_pool() is shared
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


class TestScenarioPanelPool:
    def test_panel_runs_inline_when_there_is_no_shared_pool(self, monkeypatch: pytest.MonkeyPatch):
        """max_workers = 1 means no shared pool; the panel must not start its own (nit 4)."""
        from gin_rummy.web.scenario_session import ScenarioSession

        cfg = make_mc_config(max_workers=1)
        monkeypatch.setattr(config_module, "_config", cfg)
        workers.shutdown_worker_pool()
        assert workers.get_worker_pool() is None

        scenario = ScenarioSession(mc_workers=workers.worker_count(), pool=workers.get_worker_pool())
        mc = next(m.ai for m in scenario._ensure_panel() if isinstance(m.ai, MonteCarloAI))
        assert mc._get_pool() is None and not mc._owns_pool
        scenario.shutdown()


class TestResetForNewHand:
    def test_monte_carlo_forgets_turn_plan_and_thinking(self):
        ai = MonteCarloAI(make_mc_config(max_workers=1))
        ai._turn_plan = {"discard": None, "knock": True}
        ai.last_mc_thinking = MCThinking()
        ai.reset_for_new_hand()
        assert ai._turn_plan is None and ai.last_mc_thinking is None


class TestPooledDecisions:
    def test_decisions_run_through_a_real_process_pool(self):
        """SimParams and the batch functions must pickle: every option is a pool task."""
        from tests.helpers import make_context

        pool = ProcessPoolExecutor(max_workers=2)
        try:
            ai = MonteCarloAI(make_mc_config(max_workers=2), pool=pool)
            hand = Hand([Card.parse(c) for c in ["AS", "2S", "3S", "7H", "8H", "9D", "JC", "QC", "KD", "5C"]])
            top = Card.parse("4S")
            ctx = make_context(hand)
            assert ai.decide_draw(hand, top, ctx) in (DrawChoice.DECK, DrawChoice.DISCARD)
            eleven = Hand([*hand, top])
            assert ai.decide_discard(eleven, ctx) in list(eleven)
            assert ai.should_knock(hand, ctx, pending_discard=Card.parse("KD")) in (True, False)
        finally:
            pool.shutdown(wait=True)
