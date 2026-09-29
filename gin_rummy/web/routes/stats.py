"""Player statistics."""

from fastapi import APIRouter, HTTPException

from gin_rummy.db import (
    GameTracker,
    delete_player_stats,
    get_all_players,
)

router = APIRouter()


@router.get("/api/stats/{player_name}")
async def get_player_stats(player_name: str):
    """Get lifetime statistics for a player."""
    tracker = GameTracker()
    stats = tracker.get_player_stats(player_name)
    if stats is None:
        return {"player_name": player_name, "total_hands": 0, "message": "No stats available for this player yet"}
    return stats


@router.get("/api/players")
async def get_all_players_endpoint():
    """Get list of all players with stats."""
    players = get_all_players()
    return players


@router.delete("/api/stats/{player_name}")
async def delete_player_stats_endpoint(player_name: str):
    """Delete all statistics for a specific player."""
    success = delete_player_stats(player_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Player '{player_name}' not found")
    return {"message": f"Stats deleted for player '{player_name}'", "success": True}
