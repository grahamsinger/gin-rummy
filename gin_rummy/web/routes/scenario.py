"""The scenario quiz API."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from gin_rummy.web.sessions import _get_scenario_session

router = APIRouter()


class NewScenarioRequest(BaseModel):
    seed: int | None = None


class ScenarioDrawRequest(BaseModel):
    source: Literal["deck", "discard"]


class ScenarioDiscardRequest(BaseModel):
    card: str  # Card ID like "7H"


class ScenarioKnockRequest(BaseModel):
    knock: bool


def _scenario_result(result: dict) -> dict:
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/scenario/new")
def scenario_new(req: NewScenarioRequest, request: Request, response: Response):
    """Generate a fresh scenario position."""
    scenario = _get_scenario_session(request, response)
    with scenario.owner_lock:
        return _scenario_result(scenario.new_scenario(seed=req.seed))


@router.get("/api/scenario/state")
def scenario_state(request: Request, response: Response):
    """Current scenario state (for page reloads)."""
    scenario = _get_scenario_session(request, response)
    with scenario.owner_lock:
        return scenario.get_state()


@router.post("/api/scenario/draw")
def scenario_draw(req: ScenarioDrawRequest, request: Request, response: Response):
    """Answer the draw decision; returns the panel reveal and drawn card."""
    scenario = _get_scenario_session(request, response)
    with scenario.owner_lock:
        return _scenario_result(scenario.answer_draw(req.source))


@router.post("/api/scenario/discard")
def scenario_discard(req: ScenarioDiscardRequest, request: Request, response: Response):
    """Answer the discard decision; returns the panel reveal."""
    scenario = _get_scenario_session(request, response)
    with scenario.owner_lock:
        return _scenario_result(scenario.answer_discard(req.card))


@router.post("/api/scenario/knock")
def scenario_knock(req: ScenarioKnockRequest, request: Request, response: Response):
    """Answer the knock decision; returns the panel reveal."""
    scenario = _get_scenario_session(request, response)
    with scenario.owner_lock:
        return _scenario_result(scenario.answer_knock(req.knock))
