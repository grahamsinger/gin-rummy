"""The scenario quiz API."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from gin_rummy.web.routes.common import ok
from gin_rummy.web.sessions import ScenarioDep

router = APIRouter()


class NewScenarioRequest(BaseModel):
    seed: int | None = None


class ScenarioDrawRequest(BaseModel):
    source: Literal["deck", "discard"]


class ScenarioDiscardRequest(BaseModel):
    card: str  # Card ID like "7H"


class ScenarioKnockRequest(BaseModel):
    knock: bool


class DeepAnalysisRequest(BaseModel):
    decision: Literal["draw", "discard", "knock"]


@router.post("/api/scenario/new")
def scenario_new(req: NewScenarioRequest, scenario: ScenarioDep):
    """Generate a fresh scenario position."""
    with scenario.owner_lock:
        return ok(scenario.new_scenario(seed=req.seed))


@router.get("/api/scenario/state")
def scenario_state(scenario: ScenarioDep):
    """Current scenario state (for page reloads)."""
    with scenario.owner_lock:
        return scenario.get_state()


@router.post("/api/scenario/draw")
def scenario_draw(req: ScenarioDrawRequest, scenario: ScenarioDep):
    """Answer the draw decision; returns the panel reveal and drawn card."""
    with scenario.owner_lock:
        return ok(scenario.answer_draw(req.source))


@router.post("/api/scenario/discard")
def scenario_discard(req: ScenarioDiscardRequest, scenario: ScenarioDep):
    """Answer the discard decision; returns the panel reveal."""
    with scenario.owner_lock:
        return ok(scenario.answer_discard(req.card))


@router.post("/api/scenario/knock")
def scenario_knock(req: ScenarioKnockRequest, scenario: ScenarioDep):
    """Answer the knock decision; returns the panel reveal."""
    with scenario.owner_lock:
        return ok(scenario.answer_knock(req.knock))


@router.post("/api/scenario/deep")
def scenario_deep(req: DeepAnalysisRequest, scenario: ScenarioDep):
    """Start a deep analysis of an answered decision; progress and result arrive with the state."""
    with scenario.owner_lock:
        return ok(scenario.start_deep_analysis(req.decision))
