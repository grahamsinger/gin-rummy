"""Tests for the web scenario-quiz session flow."""

from gin_rummy.web.scenario_session import ScenarioSession


def make_session() -> ScenarioSession:
    # Tiny MC budget, sequential: fast and deterministic enough for tests
    return ScenarioSession(mc_sims=10, mc_workers=1)


class TestScenarioFlow:
    def test_full_flow(self):
        s = make_session()
        state = s.new_scenario(seed=42)

        assert state["phase"] == "draw"
        assert len(state["hand"]) == 10
        assert state["discard_top"] is not None
        assert state["scenario_num"] == 1

        # Draw from deck
        state = s.answer_draw("deck")
        assert state["phase"] == "discard"
        assert len(state["hand"]) == 11
        assert state["drawn_card"] is not None
        # Nothing is revealed mid-scenario: the draw reasoning can name the discard
        assert state["reveals"] == {}

        # Discard the first non-blocked card
        blocked = state.get("blocked_card")
        card_id = next(c["id"] for c in state["hand"] if c["id"] != blocked)
        state = s.answer_discard(card_id)
        assert state["phase"] in ("knock", "done")

        # Knock decision only if eligible
        if state["phase"] == "knock":
            assert state["reveals"] == {}
            state = s.answer_knock(False)
            assert state["phase"] == "done"
            assert len(state["reveals"]["knock"]) == 3

        # Complete: every decision is revealed together
        assert state["pending"] == []
        reveal = state["reveals"]["draw"]
        assert len(reveal) == 3
        assert all("reasoning" in r and "agrees" in r for r in reveal)
        mc = next(r for r in reveal if r["name"] == "MonteCarloAI")
        assert mc["choice"] in ("deck", "discard")
        reveal = state["reveals"]["discard"]
        assert len(reveal) == 3
        mc = next(r for r in reveal if r["name"] == "MonteCarloAI")
        assert mc["mc_evs"] is None or len(mc["mc_evs"]) >= 1

        # Tallies recorded a decision per answered question
        assert s.decisions["draw"] == 1
        assert s.decisions["discard"] == 1
        s.shutdown()

    def test_wrong_phase_errors(self):
        s = make_session()
        assert "error" in s.answer_draw("deck")  # no scenario yet

        s.new_scenario(seed=42)
        assert "error" in s.answer_discard("7H")  # still in draw phase
        assert "error" in s.answer_knock(True)
        s.shutdown()

    def test_discard_validation(self):
        s = make_session()
        state = s.new_scenario(seed=42)
        s.answer_draw("discard")  # take the pile card

        # Discarding the just-taken card must be rejected
        taken = state["discard_top"]["id"]
        result = s.answer_discard(taken)
        assert "error" in result

        # Card not in hand
        current = s.get_state()
        not_held = next(cid for cid in ("AS", "KH", "7D", "2C", "9S") if cid not in [c["id"] for c in current["hand"]])
        assert "error" in s.answer_discard(not_held)

        # Junk id
        assert "error" in s.answer_discard("ZZ")
        s.shutdown()

    def test_new_scenario_resets_position_keeps_tallies(self):
        s = make_session()
        s.new_scenario(seed=42)
        s.answer_draw("deck")
        tallies_before = {k: dict(v) for k, v in s.tallies.items()}

        state = s.new_scenario(seed=43)
        assert state["phase"] == "draw"
        assert state["scenario_num"] == 2
        assert state["reveals"] == {}
        # Session tallies persist across scenarios
        assert s.tallies == tallies_before
        s.shutdown()


class TestLifetimeScoreboard:
    """Answers are saved to the database, so the scoreboard outlives the session."""

    def test_totals_survive_a_new_session(self):
        first = make_session()
        first.new_scenario(seed=42)
        first.answer_draw("deck")
        agreed = {r["name"]: r["agrees"] for r in first.reveals["draw"]}
        first.shutdown()

        # A fresh session (as after a server restart) starts from the saved totals
        second = make_session()
        lifetime = second.get_state()["lifetime"]
        assert lifetime["scenarios"] == 1
        assert set(lifetime["by_ai"]) == set(agreed)
        for name, agrees in agreed.items():
            assert lifetime["by_ai"][name]["draw"] == {"agree": int(agrees), "total": 1}
            assert lifetime["by_ai"][name]["discard"] == {"agree": 0, "total": 0}

        second.new_scenario(seed=43)
        lifetime = second.answer_draw("discard")["lifetime"]
        assert lifetime["scenarios"] == 2
        assert all(per_ai["draw"]["total"] == 2 for per_ai in lifetime["by_ai"].values())
        second.shutdown()

    def test_answers_are_stored_with_seed_and_choices(self, isolated_db):
        import sqlite3

        s = make_session()
        s.new_scenario(seed=42)
        s.answer_draw("deck")
        s.shutdown()

        with sqlite3.connect(isolated_db) as conn:
            rows = conn.execute(
                "SELECT seed, decision, user_choice, ai_name, ai_choice, agrees FROM scenario_answers ORDER BY id"
            ).fetchall()
        assert [(r[0], r[1], r[2]) for r in rows] == [(42, "draw", "deck")] * 3
        assert [(r[3], r[4], bool(r[5])) for r in rows] == [
            (r["name"], r["choice"], r["agrees"]) for r in s.reveals["draw"]
        ]

    def test_quiz_continues_when_the_database_fails(self, monkeypatch):
        import sqlite3

        import gin_rummy.web.scenario_session as module

        def broken(*args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(module, "record_scenario_answers", broken)
        monkeypatch.setattr(module, "get_scenario_totals", broken)

        s = make_session()
        s.new_scenario(seed=42)
        state = s.answer_draw("deck")
        assert state["phase"] == "discard"
        assert state["lifetime"] is None
        assert s.decisions["draw"] == 1  # session tallies still work as the fallback
        s.shutdown()


class TestBackgroundAnalysis:
    """In the web app the panel runs on a worker thread, so answering never waits for it."""

    def test_answers_return_before_the_analysis_and_reveal_at_the_end(self, monkeypatch):
        import threading

        import gin_rummy.web.scenario_session as module

        release = threading.Event()
        real_draw_choices = module.panel_draw_choices

        def slow_draw_choices(panel, game):
            assert release.wait(timeout=10)
            return real_draw_choices(panel, game)

        monkeypatch.setattr(module, "panel_draw_choices", slow_draw_choices)

        s = ScenarioSession(mc_sims=10, mc_workers=1, background=True)
        s.new_scenario(seed=42)

        # The draw is applied at once, while its analysis is still held up
        state = s.answer_draw("deck")
        assert state["phase"] == "discard" and state["pending"] == ["draw"]
        assert state["reveals"] == {}

        blocked = state.get("blocked_card")
        state = s.answer_discard(next(c["id"] for c in state["hand"] if c["id"] != blocked))
        if state["phase"] == "knock":
            state = s.answer_knock(False)
        assert state["phase"] == "done"
        assert state["pending"][0] == "draw" and state["reveals"] == {}

        release.set()
        s.wait_for_analysis()
        state = s.get_state()
        assert state["pending"] == []
        assert set(state["reveals"]) >= {"draw", "discard"}
        assert state["lifetime"]["scenarios"] == 1
        s.shutdown()

    def test_analysis_uses_the_position_as_it_was_when_answered(self):
        sync = make_session()
        sync.new_scenario(seed=42)
        state = sync.answer_draw("deck")
        blocked = state.get("blocked_card")
        card = next(c["id"] for c in state["hand"] if c["id"] != blocked)
        sync.answer_discard(card)
        expected = [(r["name"], r["choice"]) for r in sync.reveals["draw"][:2]]
        sync.shutdown()

        # Background: both answers are in before any analysis has to have run
        s = ScenarioSession(mc_sims=10, mc_workers=1, background=True)
        s.new_scenario(seed=42)
        s.answer_draw("deck")
        s.answer_discard(card)
        s.wait_for_analysis()
        assert [(r["name"], r["choice"]) for r in s.reveals["draw"][:2]] == expected
        s.shutdown()

    def test_new_scenario_waits_for_the_old_analysis(self):
        s = ScenarioSession(mc_sims=10, mc_workers=1, background=True)
        s.new_scenario(seed=42)
        s.answer_draw("deck")
        state = s.new_scenario(seed=43)
        assert state["pending"] == [] and state["reveals"] == {}
        assert state["lifetime"]["scenarios"] == 1  # the first answer was analysed and saved
        s.shutdown()

    def test_failed_analysis_does_not_stall_the_quiz(self, monkeypatch):
        import gin_rummy.web.scenario_session as module

        def broken(panel, game):
            raise RuntimeError("boom")

        monkeypatch.setattr(module, "panel_draw_choices", broken)
        s = ScenarioSession(mc_sims=10, mc_workers=1, background=True)
        s.new_scenario(seed=42)
        state = s.answer_draw("deck")
        assert state["phase"] == "discard"
        s.wait_for_analysis()
        assert s.get_state()["pending"] == []
        assert s.reveals["draw"] == [] and s.decisions["draw"] == 0
        s.shutdown()


class TestDeepAnalysis:
    """A deep analysis is run on request for a finished scenario and saved."""

    def finished(self, **kwargs) -> ScenarioSession:
        from concurrent.futures import ThreadPoolExecutor

        session = ScenarioSession(mc_sims=5, mc_workers=1, pool=ThreadPoolExecutor(max_workers=1), **kwargs)
        session.deep_samples = 20
        session.deep_batch = 20
        session.new_scenario(seed=20587)
        session.answer_draw("deck")
        state = session.answer_discard("5S")
        assert state["phase"] == "done"
        return session

    def test_nothing_offered_before_the_scenario_is_done(self):
        session = ScenarioSession(mc_sims=5, mc_workers=1)
        state = session.new_scenario(seed=20587)
        assert state["deep"] == {}
        assert "error" in session.start_deep_analysis("draw")

    def test_answered_decisions_can_be_analysed(self):
        session = self.finished()
        state = session.get_state()
        assert set(state["deep"]) == {"draw", "discard"}
        assert state["deep"]["discard"] == {"status": "none", "progress": "", "result": None, "your_choice": "5S"}
        assert "error" in session.start_deep_analysis("knock")

    def test_result_is_returned_and_saved(self):
        from gin_rummy.db.deep_analyses import list_deep_analyses

        session = self.finished()
        deep = session.start_deep_analysis("discard")["deep"]["discard"]
        assert deep["status"] == "done"
        assert deep["result"]["position"]["seed"] == 20587
        assert [row["decision"] for row in list_deep_analyses()] == ["discard"]

    def test_saved_result_is_shown_the_next_time(self):
        self.finished().start_deep_analysis("discard")
        again = self.finished().get_state()["deep"]
        assert again["discard"]["status"] == "done"
        assert again["draw"]["status"] == "none"

    def test_background_run_reports_progress_then_finishes(self):
        session = self.finished(background=True)
        try:
            state = session.start_deep_analysis("draw")
            assert state["deep"]["draw"]["status"] in ("queued", "running", "done")
            thread = session._deep_thread
            assert thread is not None
            thread.shutdown(wait=True)
            session._deep_thread = None
            assert session.get_state()["deep"]["draw"]["status"] == "done"
        finally:
            session.shutdown()
