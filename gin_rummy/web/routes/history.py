"""History: resumable games, hand turns with AI reasoning, the game list, deletion and cleanup."""

from fastapi import APIRouter, HTTPException

from gin_rummy.db import (
    cleanup_empty_games,
    delete_game,
    get_ai_decisions_for_turn,
    get_connection,
    get_hand_turns,
    get_incomplete_games,
)
from gin_rummy.models import Card, analyze_hand

router = APIRouter()


@router.get("/api/games/resumable")
async def get_resumable_games(player_name: str | None = None):
    """Get list of in-progress games that can be resumed."""
    games = get_incomplete_games(player_name=player_name)
    return {"games": games}


def _analyze_cards_for_display(card_strs: list[str]) -> dict:
    """Analyze a list of card strings and return display info with melds.

    Returns dict with:
        - cards: list of card strings in display order (melds first, then deadwood by rank)
        - melds: list of meld info [{cards: [...], type: 'set'|'run'}, ...]
    """
    if not card_strs:
        return {"cards": [], "melds": []}

    # Parse cards
    cards = [Card.parse(s) for s in card_strs]

    # Analyze for melds
    analysis = analyze_hand(cards)

    # Build set of melded cards
    melded_cards = set()
    melds_info = []
    for meld in analysis.melds:
        meld_cards = [c.code for c in meld.cards]
        melded_cards.update(meld.cards)
        melds_info.append(
            {
                "cards": meld_cards,
                "type": meld.meld_type.name.lower(),  # 'set' or 'run'
            }
        )

    # Build display order: melds first (sorted within), then deadwood sorted by rank
    display_cards = []

    # Add meld cards (sorted by rank within each meld)
    for meld in analysis.melds:
        sorted_meld = sorted(meld.cards, key=lambda c: c.rank.value)
        display_cards.extend([c.code for c in sorted_meld])

    # Add deadwood cards sorted by rank (highest first for visibility)
    sorted_deadwood = sorted(analysis.deadwood_cards, key=lambda c: -c.rank.value)
    display_cards.extend([c.code for c in sorted_deadwood])

    return {
        "cards": display_cards,
        "melds": melds_info,
    }


@router.get("/api/hands/{hand_id}/turns")
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
        if turn_dict.get("cards_before"):
            cards_before = json.loads(turn_dict["cards_before"])
            analysis_before = _analyze_cards_for_display(cards_before)
            turn_dict["cards_before"] = analysis_before["cards"]
            turn_dict["melds_before"] = analysis_before["melds"]
        if turn_dict.get("cards_after"):
            cards_after = json.loads(turn_dict["cards_after"])
            analysis_after = _analyze_cards_for_display(cards_after)
            turn_dict["cards_after"] = analysis_after["cards"]
            turn_dict["melds_after"] = analysis_after["melds"]

        # Get AI decisions for this turn
        ai_decisions = get_ai_decisions_for_turn(turn_dict["id"])
        turn_dict["ai_decisions"] = [
            {
                "decision_type": d["decision_type"],
                "choice": d["choice"],
                "reasoning": d["reasoning"],
                "factors": json.loads(d["options_considered"]) if d["options_considered"] else [],
            }
            for d in ai_decisions
        ]

        result.append(turn_dict)

    return {"hand_id": hand_id, "turns": result}


@router.get("/api/history")
async def get_history(player_name: str | None = None, limit: int = 50, offset: int = 0):
    """Get game and hand history with optional filtering.

    Args:
        player_name: Filter by player name (optional)
        limit: Maximum number of games to return (default 50)
        offset: Number of games to skip for pagination (default 0)
    """

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
                (game["game_id"],),
            )
            game["hands"] = [dict(h) for h in hands_cursor.fetchall()]

    # Filter out games with no hands (all hands had no turn data)
    games = [g for g in games if g["hands"]]

    return {"games": games, "limit": limit, "offset": offset}


@router.delete("/api/games/{game_id}")
async def delete_game_endpoint(game_id: int):
    """Delete a game and all its related data."""
    success = delete_game(game_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return {"message": f"Game {game_id} deleted", "success": True}


@router.post("/api/admin/cleanup")
async def run_cleanup():
    """Clean up games and hands with no turn data."""
    result = cleanup_empty_games()
    return {"message": f"Cleaned up {result['games']} games and {result['hands']} hands", **result}
