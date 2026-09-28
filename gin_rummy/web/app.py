"""FastAPI web application for Gin Rummy."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gin_rummy.config import get_config
from gin_rummy.web.game_session import GameSession
from gin_rummy.web.session_store import SessionStore
from gin_rummy.database import (
    get_game_hands, get_all_players, delete_player_stats,
    get_hand_turns, get_connection, cleanup_empty_games,
    get_ai_decisions_for_turn, db_list_to_cards, card_to_db_str,
    delete_game, GameTracker, get_incomplete_games, init_db,
)
from gin_rummy.models import analyze_hand


# Initialize logging from config
config = get_config()
config.setup_logging()

# Session store and cookie config
session_store = SessionStore()
COOKIE_NAME = "gin_session_id"
COOKIE_MAX_AGE = 4 * 60 * 60  # 4 hours


def get_or_create_session(request: Request, response: Response) -> GameSession:
    """Get existing session from cookie or create a new one."""
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        session = session_store.get_session(session_id)
        if session is not None:
            # Refresh cookie expiry to match server-side touch
            response.set_cookie(
                key=COOKIE_NAME,
                value=session_id,
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
            )
            return session

    # Create new session
    session_id, session = session_store.create_session()
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return session


# Lifespan: create the DB schema up front, then periodically clean up expired sessions
@asynccontextmanager
async def lifespan(app: FastAPI):
    # History/stats routes query the DB directly, so the schema must exist
    # before any GameSession has created a GameTracker.
    init_db()

    async def cleanup_loop():
        while True:
            await asyncio.sleep(10 * 60)  # every 10 minutes
            session_store.cleanup_expired()

    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


# Create FastAPI app
app = FastAPI(title="Gin Rummy", lifespan=lifespan)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Request models
class NewGameRequest(BaseModel):
    player_name: str | None = None  # Player's name
    ai_difficulty: str | None = None  # "easy", "medium", or "hard"
    game_mode: str | None = None  # "practice" or "target"
    target_score: int | None = None  # Target score for "target" mode (100, 150, 200, 250)
    oklahoma_gin: bool | None = None  # Whether to use Oklahoma Gin rules
    spade_doubling: bool | None = None  # Whether to double points when upcard is a spade
    match_mode: bool | None = None  # Whether to play best-of-3 match


class ResumeGameRequest(BaseModel):
    game_id: int


class DrawRequest(BaseModel):
    source: str  # "deck" or "discard"


class DiscardRequest(BaseModel):
    card: str  # Card ID like "7H" or "10S"
    knock: bool | None = None  # None = check if can knock, True/False = execute


logger = logging.getLogger("gin_rummy.web")
ai_logger = logging.getLogger("gin_rummy.ai")


# Log test endpoints
@app.get("/log/{level}")
async def log_test(level: str):
    """Emit a test log message at the given level. Useful for verifying logging config."""
    level = level.upper()
    log_func = getattr(logger, level.lower(), None)
    ai_log_func = getattr(ai_logger, level.lower(), None)
    if log_func is None:
        return {"error": f"Unknown log level: {level}", "valid": "debug, info, warning, error, critical"}
    msg = f"Test log message at {level} level"
    log_func(msg)
    ai_log_func(f"[AI] {msg}")
    return {
        "level": level,
        "message": msg,
        "root_logger_level": logging.getLevelName(logging.getLogger().level),
        "ai_logger_level": logging.getLevelName(ai_logger.level),
        "log_file": config.logging.log_file,
    }


# Routes
@app.get("/")
async def index():
    """Serve the main game page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/game/new")
async def new_game(request: Request, response: Response, game_request: NewGameRequest | None = None):
    """Start a new game with optional settings."""
    session = get_or_create_session(request, response)
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


@app.get("/api/game/state")
async def get_state(request: Request, response: Response):
    """Get current game state."""
    session = get_or_create_session(request, response)
    return session.get_state()


@app.post("/api/game/draw")
async def draw(request: Request, response: Response, draw_request: DrawRequest):
    """Draw a card from deck or discard pile."""
    session = get_or_create_session(request, response)
    result = session.draw(draw_request.source)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/discard")
async def discard(request: Request, response: Response, discard_request: DiscardRequest):
    """Discard a card from hand, optionally knocking."""
    session = get_or_create_session(request, response)
    result = session.discard(discard_request.card, knock=discard_request.knock)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/knock")
async def knock(request: Request, response: Response):
    """Knock to end the round."""
    session = get_or_create_session(request, response)
    result = session.knock()
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/ai-turn")
async def ai_turn(request: Request, response: Response):
    """Execute AI's turn."""
    session = get_or_create_session(request, response)
    result = session.ai_turn()
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/new-round")
async def new_round(request: Request, response: Response):
    """Start a new round."""
    session = get_or_create_session(request, response)
    result = session.new_round()
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.post("/api/game/resume")
async def resume_game(request: Request, response: Response, resume_request: ResumeGameRequest):
    """Resume an incomplete game by ID."""
    session = get_or_create_session(request, response)
    result = session.resume_game(resume_request.game_id)
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.get("/api/games/resumable")
async def get_resumable_games(player_name: str | None = None):
    """Get list of in-progress games that can be resumed."""
    games = get_incomplete_games(player_name=player_name)
    return {'games': games}


@app.get("/api/stats/{player_name}")
async def get_player_stats(player_name: str):
    """Get lifetime statistics for a player."""
    tracker = GameTracker()
    stats = tracker.get_player_stats(player_name)
    if stats is None:
        return {
            'player_name': player_name,
            'total_hands': 0,
            'message': 'No stats available for this player yet'
        }
    return stats


@app.get("/api/players")
async def get_all_players_endpoint():
    """Get list of all players with stats."""
    players = get_all_players()
    return players


@app.delete("/api/stats/{player_name}")
async def delete_player_stats_endpoint(player_name: str):
    """Delete all statistics for a specific player."""
    success = delete_player_stats(player_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")
    return {"message": f"Stats deleted for player '{player_name}'", "success": True}


@app.get("/api/game/score-history")
async def get_score_history(request: Request, response: Response):
    """Get round-by-round score history for current game."""
    session = get_or_create_session(request, response)

    # Check if a game is in progress
    if not hasattr(session, 'tracker') or session.tracker.game_id is None:
        return {
            'player1_name': '',
            'player2_name': '',
            'rounds': []
        }

    # Get player names
    player1_name = session.game.players[0].name
    player2_name = session.game.players[1].name

    # Get all hands for this game
    hands = get_game_hands(session.tracker.game_id)

    if not hands:
        return {
            'player1_name': player1_name,
            'player2_name': player2_name,
            'rounds': []
        }

    # Get turn counts for each hand
    with get_connection() as conn:
        hand_ids = [h['id'] for h in hands]
        placeholders = ','.join('?' * len(hand_ids))
        cursor = conn.execute(
            f"SELECT hand_id, COUNT(*) as turn_count FROM turns WHERE hand_id IN ({placeholders}) GROUP BY hand_id",
            hand_ids
        )
        turn_counts = {row['hand_id']: row['turn_count'] for row in cursor.fetchall()}

    # Calculate cumulative scores
    cumulative_p1 = 0
    cumulative_p2 = 0
    rounds = []

    for hand in hands:
        # Skip incomplete hands (in-progress rounds)
        if hand['points_awarded'] is None:
            continue

        # Skip hands without turn data (human never played)
        if turn_counts.get(hand['id'], 0) == 0:
            continue

        # Add points to winner
        if hand['winner_name'] == player1_name:
            cumulative_p1 += hand['points_awarded']
        elif hand['winner_name'] == player2_name:
            cumulative_p2 += hand['points_awarded']
        # else: draw, no points awarded

        rounds.append({
            'hand_id': hand['id'],
            'hand_number': hand['hand_number'],
            'winner': hand['winner_name'],
            'points': hand['points_awarded'],
            'cumulative_p1': cumulative_p1,
            'cumulative_p2': cumulative_p2,
            'is_gin': hand['is_gin'],
            'is_undercut': hand['is_undercut'],
            'is_draw': hand['is_draw']
        })

    return {
        'player1_name': player1_name,
        'player2_name': player2_name,
        'rounds': rounds
    }


def _analyze_cards_for_display(card_strs: list[str]) -> dict:
    """Analyze a list of card strings and return display info with melds.

    Returns dict with:
        - cards: list of card strings in display order (melds first, then deadwood by rank)
        - melds: list of meld info [{cards: [...], type: 'set'|'run'}, ...]
    """
    if not card_strs:
        return {'cards': [], 'melds': []}

    # Parse cards
    cards = db_list_to_cards(card_strs)

    # Analyze for melds
    analysis = analyze_hand(cards)

    # Build set of melded cards
    melded_cards = set()
    melds_info = []
    for meld in analysis.melds:
        meld_cards = [card_to_db_str(c) for c in meld.cards]
        melded_cards.update(meld.cards)
        melds_info.append({
            'cards': meld_cards,
            'type': meld.meld_type.name.lower()  # 'set' or 'run'
        })

    # Build display order: melds first (sorted within), then deadwood sorted by rank
    display_cards = []

    # Add meld cards (sorted by rank within each meld)
    for meld in analysis.melds:
        sorted_meld = sorted(meld.cards, key=lambda c: c.rank.value)
        display_cards.extend([card_to_db_str(c) for c in sorted_meld])

    # Add deadwood cards sorted by rank (highest first for visibility)
    sorted_deadwood = sorted(analysis.deadwood_cards, key=lambda c: -c.rank.value)
    display_cards.extend([card_to_db_str(c) for c in sorted_deadwood])

    return {
        'cards': display_cards,
        'melds': melds_info,
    }


@app.get("/api/hands/{hand_id}/turns")
async def get_turns_for_hand(hand_id: int):
    """Get all turns for a specific hand, including AI decision reasoning."""
    import json
    turns = get_hand_turns(hand_id)

    if not turns:
        raise HTTPException(status_code=404, detail=f"No turns found for hand {hand_id}")

    # Convert sqlite3.Row objects to dicts and parse JSON fields
    result = []
    for turn in turns:
        turn_dict = dict(turn)
        # Parse JSON fields and add meld analysis
        if turn_dict.get('cards_before'):
            cards_before = json.loads(turn_dict['cards_before'])
            analysis_before = _analyze_cards_for_display(cards_before)
            turn_dict['cards_before'] = analysis_before['cards']
            turn_dict['melds_before'] = analysis_before['melds']
        if turn_dict.get('cards_after'):
            cards_after = json.loads(turn_dict['cards_after'])
            analysis_after = _analyze_cards_for_display(cards_after)
            turn_dict['cards_after'] = analysis_after['cards']
            turn_dict['melds_after'] = analysis_after['melds']

        # Get AI decisions for this turn
        ai_decisions = get_ai_decisions_for_turn(turn_dict['id'])
        turn_dict['ai_decisions'] = [
            {
                'decision_type': d['decision_type'],
                'choice': d['choice'],
                'reasoning': d['reasoning'],
                'factors': json.loads(d['options_considered']) if d['options_considered'] else [],
            }
            for d in ai_decisions
        ]

        result.append(turn_dict)

    return {'hand_id': hand_id, 'turns': result}


@app.get("/api/history")
async def get_history(
    player_name: str | None = None,
    limit: int = 50,
    offset: int = 0
):
    """Get game and hand history with optional filtering.

    Args:
        player_name: Filter by player name (optional)
        limit: Maximum number of games to return (default 50)
        offset: Number of games to skip for pagination (default 0)
    """
    import json

    with get_connection() as conn:
        # Build query with optional player filter
        if player_name:
            query = """
                SELECT g.id as game_id, g.player1_name, g.player2_name,
                       g.started_at, g.ended_at, g.winner_name,
                       g.final_score_p1, g.final_score_p2,
                       g.oklahoma_gin, g.spade_doubling, g.game_mode,
                       g.target_score, g.ai_difficulty, g.match_mode,
                       g.match_id,
                       COUNT(h.id) as hand_count
                FROM games g
                LEFT JOIN hands h ON g.id = h.game_id
                    AND EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = h.id)
                WHERE g.player1_name = ? OR g.player2_name = ?
                GROUP BY g.id
                ORDER BY g.started_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(query, (player_name, player_name, limit, offset))
        else:
            query = """
                SELECT g.id as game_id, g.player1_name, g.player2_name,
                       g.started_at, g.ended_at, g.winner_name,
                       g.final_score_p1, g.final_score_p2,
                       g.oklahoma_gin, g.spade_doubling, g.game_mode,
                       g.target_score, g.ai_difficulty, g.match_mode,
                       g.match_id,
                       COUNT(h.id) as hand_count
                FROM games g
                LEFT JOIN hands h ON g.id = h.game_id
                    AND EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = h.id)
                GROUP BY g.id
                ORDER BY g.started_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(query, (limit, offset))

        games = [dict(row) for row in cursor.fetchall()]

        # Get hands for each game (only those with turn data)
        for game in games:
            hands_cursor = conn.execute(
                """SELECT h.id, h.hand_number, h.dealer_name, h.winner_name,
                          h.points_awarded, h.is_gin, h.is_undercut, h.is_draw
                   FROM hands h
                   WHERE h.game_id = ?
                     AND EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = h.id)
                   ORDER BY h.hand_number""",
                (game['game_id'],)
            )
            game['hands'] = [dict(h) for h in hands_cursor.fetchall()]

    # Filter out games with no hands (all hands had no turn data)
    games = [g for g in games if g['hands']]

    return {'games': games, 'limit': limit, 'offset': offset}


@app.delete("/api/games/{game_id}")
async def delete_game_endpoint(game_id: int):
    """Delete a game and all its related data."""
    success = delete_game(game_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return {"message": f"Game {game_id} deleted", "success": True}


@app.get("/history")
async def history_page():
    """Serve the hand history explorer page."""
    return FileResponse(STATIC_DIR / "history.html")


@app.get("/memory")
async def memory_page():
    """Serve the card memory game page."""
    return FileResponse(STATIC_DIR / "memory.html")


# ---------------------------------------------------------------------------
# Scenario quiz
# ---------------------------------------------------------------------------

class NewScenarioRequest(BaseModel):
    seed: int | None = None


class ScenarioDrawRequest(BaseModel):
    source: str  # "deck" or "discard"


class ScenarioDiscardRequest(BaseModel):
    card: str  # Card ID like "7H"


class ScenarioKnockRequest(BaseModel):
    knock: bool


def _get_scenario_session(request: Request, response: Response):
    from gin_rummy.web.scenario_session import ScenarioSession

    session = get_or_create_session(request, response)
    if session.scenario_session is None:
        session.scenario_session = ScenarioSession()
    return session.scenario_session


def _scenario_result(result: dict) -> dict:
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@app.get("/scenario")
async def scenario_page():
    """Serve the scenario quiz page."""
    return FileResponse(STATIC_DIR / "scenario.html")


@app.post("/api/scenario/new")
async def scenario_new(req: NewScenarioRequest, request: Request, response: Response):
    """Generate a fresh scenario position."""
    scenario = _get_scenario_session(request, response)
    return _scenario_result(scenario.new_scenario(seed=req.seed))


@app.get("/api/scenario/state")
async def scenario_state(request: Request, response: Response):
    """Current scenario state (for page reloads)."""
    scenario = _get_scenario_session(request, response)
    return scenario.get_state()


@app.post("/api/scenario/draw")
async def scenario_draw(req: ScenarioDrawRequest, request: Request, response: Response):
    """Answer the draw decision; returns the panel reveal and drawn card."""
    scenario = _get_scenario_session(request, response)
    return _scenario_result(scenario.answer_draw(req.source))


@app.post("/api/scenario/discard")
async def scenario_discard(req: ScenarioDiscardRequest, request: Request, response: Response):
    """Answer the discard decision; returns the panel reveal."""
    scenario = _get_scenario_session(request, response)
    return _scenario_result(scenario.answer_discard(req.card))


@app.post("/api/scenario/knock")
async def scenario_knock(req: ScenarioKnockRequest, request: Request, response: Response):
    """Answer the knock decision; returns the panel reveal."""
    scenario = _get_scenario_session(request, response)
    return _scenario_result(scenario.answer_knock(req.knock))


@app.post("/api/admin/cleanup")
async def run_cleanup():
    """Clean up games and hands with no turn data."""
    result = cleanup_empty_games()
    return {
        "message": f"Cleaned up {result['games']} games and {result['hands']} hands",
        **result
    }
