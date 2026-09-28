"""In-memory session store keyed by cookie session ID."""

import secrets
import threading
import time

from gin_rummy.web.game_session import GameSession


class SessionEntry:
    """Wraps a GameSession with a last-accessed timestamp."""

    __slots__ = ("session", "last_accessed")

    def __init__(self, session: GameSession) -> None:
        self.session = session
        self.last_accessed = time.monotonic()

    def touch(self) -> None:
        self.last_accessed = time.monotonic()


class SessionStore:
    """Thread-safe dict of session_id -> SessionEntry."""

    def __init__(self, ttl_seconds: float = 4 * 60 * 60) -> None:
        self._sessions: dict[str, SessionEntry] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds

    def create_session(self) -> tuple[str, GameSession]:
        """Create a new session and return (session_id, GameSession)."""
        session_id = secrets.token_hex(16)
        gs = GameSession()
        entry = SessionEntry(gs)
        with self._lock:
            self._sessions[session_id] = entry
        return session_id, gs

    def get_session(self, session_id: str) -> GameSession | None:
        """Return the session if it exists and is not expired, else None."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            if time.monotonic() - entry.last_accessed > self.ttl_seconds:
                del self._sessions[session_id]
                return None
            entry.touch()
            return entry.session

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns the number removed."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired_ids = [sid for sid, entry in self._sessions.items() if now - entry.last_accessed > self.ttl_seconds]
            for sid in expired_ids:
                del self._sessions[sid]
                removed += 1
        return removed

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)
