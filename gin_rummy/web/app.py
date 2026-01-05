"""FastAPI web application for Gin Rummy."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gin_rummy.web.game_session import GameSession


# Create FastAPI app
app = FastAPI(title="Gin Rummy")

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Single game session (for now, single player)
session = GameSession()


# Request models
class NewGameRequest(BaseModel):
    player_name: str | None = None  # Player's name
    ai_difficulty: str | None = None  # "easy", "medium", or "hard"


class DrawRequest(BaseModel):
    source: str  # "deck" or "discard"


class DiscardRequest(BaseModel):
    card: str  # Card ID like "7H" or "10S"
    knock: bool | None = None  # None = check if can knock, True/False = execute


# Routes
@app.get("/")
async def index():
    """Serve the main game page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/game/new")
async def new_game(request: NewGameRequest | None = None):
    """Start a new game with optional settings.

    Args:
        request: Optional settings for player name and AI difficulty
    """
    if request:
        return session.new_game(player_name=request.player_name, ai_difficulty=request.ai_difficulty)
    return session.new_game()


@app.get("/api/game/state")
async def get_state():
    """Get current game state."""
    return session.get_state()


@app.post("/api/game/draw")
async def draw(request: DrawRequest):
    """Draw a card from deck or discard pile."""
    result = session.draw(request.source)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/discard")
async def discard(request: DiscardRequest):
    """Discard a card from hand, optionally knocking."""
    result = session.discard(request.card, knock=request.knock)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/knock")
async def knock():
    """Knock to end the round."""
    result = session.knock()
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/ai-turn")
async def ai_turn():
    """Execute AI's turn."""
    result = session.ai_turn()
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/new-round")
async def new_round():
    """Start a new round."""
    result = session.new_round()
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result
