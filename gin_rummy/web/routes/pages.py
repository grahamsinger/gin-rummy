"""Static pages and the logging test endpoint."""

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from gin_rummy.config import get_config

config = get_config()

router = APIRouter()


# Static files directory
STATIC_DIR = Path(__file__).parent.parent / "static"  # gin_rummy/web/static


logger = logging.getLogger("gin_rummy.web")
ai_logger = logging.getLogger("gin_rummy.ai")


# Log test endpoints
@router.get("/log/{level}")
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


@router.get("/")
async def index():
    """Serve the main game page."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/history")
async def history_page():
    """Serve the hand history explorer page."""
    return FileResponse(STATIC_DIR / "history.html")


@router.get("/memory")
async def memory_page():
    """Serve the card memory game page."""
    return FileResponse(STATIC_DIR / "memory.html")


@router.get("/scenario")
async def scenario_page():
    """Serve the scenario quiz page."""
    return FileResponse(STATIC_DIR / "scenario.html")
