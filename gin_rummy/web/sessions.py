"""Browser sessions: the cookie, the store, and how a request finds its GameSession and ScenarioSession."""

from fastapi import Request, Response

from gin_rummy.web.game_session import GameSession
from gin_rummy.web.session_store import SessionStore
from gin_rummy.web.workers import get_worker_pool, worker_count

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


def _get_scenario_session(request: Request, response: Response):
    from gin_rummy.web.scenario_session import ScenarioSession

    session = get_or_create_session(request, response)
    with session.lock:
        if session.scenario_session is None:
            # mc_workers matches the shared pool, so when there is no shared
            # pool (max_workers = 1) the panel runs inline instead of starting
            # its own processes.
            scenario = ScenarioSession(mc_workers=worker_count(), pool=get_worker_pool())
            scenario.owner_lock = session.lock
            session.scenario_session = scenario
        return session.scenario_session
