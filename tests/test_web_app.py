"""End-to-end tests for the FastAPI app using TestClient.

The autouse ``isolated_db`` fixture in conftest.py points the tracker at a
temporary database, so these tests never touch game_history.db.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gin_rummy.models import Card
from gin_rummy.web.app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _play_until_round_over(client: TestClient, max_steps: int = 120) -> dict:
    """Drive one round with a naive human policy (never knocks)."""
    for _ in range(max_steps):
        state = client.get("/api/game/state").json()
        assert "error" not in state, state
        if state["round_over"] or state["game_over"]:
            return state
        if not state["your_turn"]:
            r = client.post("/api/game/ai-turn")
            assert r.status_code == 200, r.text
            continue
        if state["phase"] == "drawing":
            r = client.post("/api/game/draw", json={"source": "deck"})
        elif state["phase"] == "discarding":
            r = client.post("/api/game/discard", json={"card": state["hand"][0]["id"], "knock": False})
        else:
            pytest.fail(f"unexpected phase {state['phase']!r} on human turn")
        assert r.status_code == 200, r.text
    pytest.fail("round did not finish")


class TestGameFlow:
    def test_new_game_state_shape(self, client: TestClient):
        r = client.post("/api/game/new", json={"player_name": "Tester", "ai_difficulty": "easy"})
        assert r.status_code == 200
        state = r.json()
        assert state["player_name"] == "Tester"
        assert state["ai_difficulty"] == "easy"
        assert len(state["hand"]) in (10, 11)
        assert set(state["scores"]) == {"Tester", "Computer"}
        assert "gin_session_id" in r.cookies

    def test_full_round_is_recorded(self, client: TestClient):
        client.post("/api/game/new", json={"player_name": "Tester", "ai_difficulty": "easy"})
        state = _play_until_round_over(client)
        assert state["round_over"] or state["game_over"]
        result = state["round_result"]
        assert result is not None
        assert result["is_draw"] or result["points"] >= 0

        # The round was written to the (temporary) database
        history = client.get("/api/game/score-history").json()
        assert len(history["rounds"]) == 1
        assert history["rounds"][0]["is_draw"] == result["is_draw"]

        # Player shows up in the players list
        players = {p["name"] for p in client.get("/api/players").json()}
        assert "Tester" in players

    def test_new_round_after_round_over(self, client: TestClient):
        client.post("/api/game/new", json={"player_name": "Tester", "ai_difficulty": "easy"})
        _play_until_round_over(client)
        r = client.post("/api/game/new-round")
        assert r.status_code == 200
        state = r.json()
        assert not state["round_over"]
        assert len(state["hand"]) in (10, 11)


class TestValidation:
    def test_draw_before_game_is_400(self, client: TestClient):
        r = client.post("/api/game/draw", json={"source": "deck"})
        assert r.status_code == 400

    def test_malformed_card_id_is_400_not_500(self, client: TestClient):
        """B14: parsing "10" used to raise IndexError and return a 500."""
        client.post("/api/game/new", json={"player_name": "Tester", "ai_difficulty": "easy"})
        for bad in ("10", "", "ZZ", "7X", "7h"):
            r = client.post("/api/game/discard", json={"card": bad})
            assert r.status_code == 400, (bad, r.status_code, r.text)

    def test_history_endpoints(self, client: TestClient):
        assert client.get("/api/history").status_code == 200
        assert client.get("/api/games/resumable").status_code == 200
        assert client.get("/history").status_code == 200
        assert client.get("/").status_code == 200


class TestCardIds:
    """The web API's card ids are Card.code / Card.parse (see test_card.py)."""

    def test_state_uses_card_codes(self, client: TestClient):
        state = client.post("/api/game/new", json={"player_name": "Tester", "ai_difficulty": "easy"}).json()
        for card in state["hand"]:
            assert Card.parse(card["id"]).code == card["id"]
