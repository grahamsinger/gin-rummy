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
        reveal = state["reveals"]["draw"]
        assert len(reveal) == 3
        assert all("reasoning" in r and "agrees" in r for r in reveal)
        mc = next(r for r in reveal if r["name"] == "MonteCarloAI")
        assert mc["choice"] in ("deck", "discard")

        # Discard the first non-blocked card
        blocked = state.get("blocked_card")
        card_id = next(c["id"] for c in state["hand"] if c["id"] != blocked)
        state = s.answer_discard(card_id)
        assert state["phase"] in ("knock", "done")
        reveal = state["reveals"]["discard"]
        assert len(reveal) == 3
        mc = next(r for r in reveal if r["name"] == "MonteCarloAI")
        assert mc["mc_evs"] is None or len(mc["mc_evs"]) >= 1

        # Knock decision only if eligible
        if state["phase"] == "knock":
            state = s.answer_knock(False)
            assert state["phase"] == "done"
            assert len(state["reveals"]["knock"]) == 3

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
        not_held = next(
            cid for cid in ("AS", "KH", "7D", "2C", "9S")
            if cid not in [c["id"] for c in current["hand"]]
        )
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
