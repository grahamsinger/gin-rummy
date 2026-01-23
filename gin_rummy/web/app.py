"""FastAPI web application for Gin Rummy."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gin_rummy.web.game_session import GameSession
from gin_rummy.database import (
    get_game_hands, get_all_players, delete_player_stats,
    get_hand_turns, get_connection, cleanup_empty_games,
    get_ai_decisions_for_turn,
)


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
    game_mode: str | None = None  # "practice" or "target"
    target_score: int | None = None  # Target score for "target" mode (100, 150, 200, 250)
    oklahoma_gin: bool | None = None  # Whether to use Oklahoma Gin rules
    spade_doubling: bool | None = None  # Whether to double points when upcard is a spade
    match_mode: bool | None = None  # Whether to play best-of-3 match


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
        request: Optional settings for player name, AI difficulty, game mode, and target score
    """
    if request:
        return session.new_game(
            player_name=request.player_name,
            ai_difficulty=request.ai_difficulty,
            game_mode=request.game_mode,
            target_score=request.target_score,
            oklahoma_gin=request.oklahoma_gin,
            spade_doubling=request.spade_doubling,
            match_mode=request.match_mode,
        )
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


@app.get("/api/stats/{player_name}")
async def get_player_stats(player_name: str):
    """Get lifetime statistics for a player."""
    stats = session.tracker.get_player_stats(player_name)
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
async def get_score_history():
    """Get round-by-round score history for current game."""
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
        # Parse JSON fields
        if turn_dict.get('cards_before'):
            turn_dict['cards_before'] = json.loads(turn_dict['cards_before'])
        if turn_dict.get('cards_after'):
            turn_dict['cards_after'] = json.loads(turn_dict['cards_after'])

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
                       COUNT(h.id) as hand_count
                FROM games g
                LEFT JOIN hands h ON g.id = h.game_id
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
                       COUNT(h.id) as hand_count
                FROM games g
                LEFT JOIN hands h ON g.id = h.game_id
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


@app.get("/history")
async def history_page():
    """Serve the hand history explorer page."""
    return FileResponse(STATIC_DIR / "history.html")


@app.post("/api/admin/cleanup")
async def run_cleanup():
    """Clean up games and hands with no turn data."""
    result = cleanup_empty_games()
    return {
        "message": f"Cleaned up {result['games']} games and {result['hands']} hands",
        **result
    }
