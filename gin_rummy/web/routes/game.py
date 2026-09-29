"""The game API: one GameSession per browser, every mutation under its lock."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from gin_rummy.db import (
    get_connection,
    get_game_hands,
)
from gin_rummy.web.game_session import GameSession
from gin_rummy.web.sessions import get_or_create_session

router = APIRouter()


# Request models
class NewGameRequest(BaseModel):
    player_name: str | None = None  # Player's name
    ai_difficulty: Literal["easy", "medium", "hard"] | None = None
    game_mode: str | None = None  # "practice" or "target"
    target_score: int | None = None  # Target score for "target" mode (100, 150, 200, 250)
    oklahoma_gin: bool | None = None  # Whether to use Oklahoma Gin rules
    spade_doubling: bool | None = None  # Whether to double points when upcard is a spade
    match_mode: bool | None = None  # Whether to play best-of-3 match


class ResumeGameRequest(BaseModel):
    game_id: int


class DrawRequest(BaseModel):
    source: Literal["deck", "discard"]


class DiscardRequest(BaseModel):
    card: str  # Card ID like "7H" or "10S"
    knock: bool | None = None  # None = check if can knock, True/False = execute


@router.post("/api/game/new")
def new_game(request: Request, response: Response, game_request: NewGameRequest | None = None):
    """Start a new game with optional settings."""
    session = get_or_create_session(request, response)
    with session.lock:
        return _new_game(session, game_request)


def _new_game(session: GameSession, game_request: NewGameRequest | None):
    if game_request:
        return session.new_game(
            player_name=game_request.player_name,
            ai_difficulty=game_request.ai_difficulty,
            game_mode=game_request.game_mode,
            target_score=game_request.target_score,
            oklahoma_gin=game_request.oklahoma_gin,
            spade_doubling=game_request.spade_doubling,
            match_mode=game_request.match_mode,
        )
    return session.new_game()


@router.get("/api/game/state")
def get_state(request: Request, response: Response):
    """Get current game state."""
    session = get_or_create_session(request, response)
    with session.lock:
        return session.get_state()


@router.post("/api/game/draw")
def draw(request: Request, response: Response, draw_request: DrawRequest):
    """Draw a card from deck or discard pile."""
    session = get_or_create_session(request, response)
    with session.lock:
        result = session.draw(draw_request.source)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/game/discard")
def discard(request: Request, response: Response, discard_request: DiscardRequest):
    """Discard a card from hand, optionally knocking."""
    session = get_or_create_session(request, response)
    with session.lock:
        result = session.discard(discard_request.card, knock=discard_request.knock)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/game/knock")
def knock(request: Request, response: Response):
    """Knock to end the round."""
    session = get_or_create_session(request, response)
    with session.lock:
        result = session.knock()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/game/ai-turn")
def ai_turn(request: Request, response: Response):
    """Execute AI's turn."""
    session = get_or_create_session(request, response)
    with session.lock:
        result = session.ai_turn()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/game/new-round")
def new_round(request: Request, response: Response):
    """Start a new round."""
    session = get_or_create_session(request, response)
    with session.lock:
        result = session.new_round()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/game/resume")
def resume_game(request: Request, response: Response, resume_request: ResumeGameRequest):
    """Resume an incomplete game by ID."""
    session = get_or_create_session(request, response)
    with session.lock:
        result = session.resume_game(resume_request.game_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/game/score-history")
async def get_score_history(request: Request, response: Response):
    """Get round-by-round score history for current game."""
    session = get_or_create_session(request, response)

    # Check if a game is in progress
    if not hasattr(session, "tracker") or session.tracker.game_id is None:
        return {"player1_name": "", "player2_name": "", "rounds": []}

    # Get player names
    player1_name = session.game.players[0].name
    player2_name = session.game.players[1].name

    # Get all hands for this game
    hands = get_game_hands(session.tracker.game_id)

    if not hands:
        return {"player1_name": player1_name, "player2_name": player2_name, "rounds": []}

    # Get turn counts for each hand
    with get_connection() as conn:
        hand_ids = [h["id"] for h in hands]
        placeholders = ",".join("?" * len(hand_ids))
        cursor = conn.execute(
            f"SELECT hand_id, COUNT(*) as turn_count FROM turns WHERE hand_id IN ({placeholders}) GROUP BY hand_id",
            hand_ids,
        )
        turn_counts = {row["hand_id"]: row["turn_count"] for row in cursor.fetchall()}

    # Calculate cumulative scores
    cumulative_p1 = 0
    cumulative_p2 = 0
    rounds = []

    for hand in hands:
        # Skip incomplete hands (in-progress rounds)
        if hand["points_awarded"] is None:
            continue

        # Skip hands without turn data (human never played)
        if turn_counts.get(hand["id"], 0) == 0:
            continue

        # Add points to winner
        if hand["winner_name"] == player1_name:
            cumulative_p1 += hand["points_awarded"]
        elif hand["winner_name"] == player2_name:
            cumulative_p2 += hand["points_awarded"]
        # else: draw, no points awarded

        rounds.append(
            {
                "hand_id": hand["id"],
                "hand_number": hand["hand_number"],
                "winner": hand["winner_name"],
                "points": hand["points_awarded"],
                "cumulative_p1": cumulative_p1,
                "cumulative_p2": cumulative_p2,
                "is_gin": hand["is_gin"],
                "is_undercut": hand["is_undercut"],
                "is_draw": hand["is_draw"],
            }
        )

    return {"player1_name": player1_name, "player2_name": player2_name, "rounds": rounds}
