"""FastAPI web application for Gin Rummy."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from gin_rummy.config import get_config
from gin_rummy.db import (
    init_db,
)
from gin_rummy.web.routes import game, history, pages, scenario, stats
from gin_rummy.web.routes.pages import STATIC_DIR
from gin_rummy.web.sessions import session_store
from gin_rummy.web.workers import shutdown_worker_pool

# Initialize logging from config
config = get_config()
config.setup_logging()


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
    session_store.close_all()
    shutdown_worker_pool()


# Create FastAPI app
app = FastAPI(title="Gin Rummy", lifespan=lifespan)


# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

for router in (pages.router, game.router, history.router, stats.router, scenario.router):
    app.include_router(router)
