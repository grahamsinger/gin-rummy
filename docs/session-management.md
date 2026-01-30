# Per-Browser Session Management

## Overview

Previously, the server used a single global `GameSession` object — every browser/tab/device shared the same game. Now each browser gets its own independent session via an HTTP cookie.

---

## New File: `session_store.py`

### `SessionEntry`

A lightweight wrapper around a `GameSession` that tracks when it was last accessed:

```python
class SessionEntry:
    def __init__(self, session: GameSession) -> None:
        self.session = session
        self.last_accessed = time.monotonic()
```

`time.monotonic()` is used instead of `time.time()` because it's immune to system clock changes (e.g., NTP adjustments, daylight saving). It only goes forward, which is all we need for measuring elapsed time.

### `SessionStore`

A thread-safe dictionary mapping session IDs to `SessionEntry` objects:

- **`create_session()`** — generates a random 32-character hex ID via `secrets.token_hex(16)`, creates a new `GameSession`, stores it, and returns both.
- **`get_session(session_id)`** — looks up the session. If it exists and hasn't exceeded the TTL (4 hours), it "touches" the timestamp (resetting the idle clock) and returns it. If expired, it deletes the entry and returns `None`.
- **`cleanup_expired()`** — iterates all sessions and removes any that have been idle longer than the TTL. Called periodically by a background task.

All operations are protected by a `threading.Lock` because FastAPI can handle requests across multiple threads (even though route handlers are `async`, the session store is plain synchronous Python).

---

## Changes to `app.py`

### Cookie-based session lookup

```python
def get_or_create_session(request: Request, response: Response) -> GameSession:
```

Every session-dependent route now calls this helper. It:

1. Reads the `gin_session_id` cookie from the incoming request
2. If the cookie exists and maps to a valid (non-expired) session, returns it
3. Otherwise, creates a new session and sets the cookie on the response

The cookie is configured as:
- **`httponly=True`** — JavaScript can't read it (XSS protection). `fetch()` sends it automatically on same-origin requests.
- **`samesite="lax"`** — the cookie is sent on same-site navigations and top-level GET requests, but not on cross-site POST requests (CSRF protection).
- **`max_age=4*60*60`** — the browser discards the cookie after 4 hours (matches the server-side TTL).

### Lifespan and the cleanup task

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async def cleanup_loop():
        while True:
            await asyncio.sleep(10 * 60)
            session_store.cleanup_expired()

    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()
```

#### What is `@asynccontextmanager`?

A context manager is anything that supports `__enter__`/`__exit__` (the `with` pattern). An *async* context manager is the `async with` equivalent. `@asynccontextmanager` is a decorator that lets you write one using a simple generator function instead of a full class:

- Everything **before `yield`** runs on startup (like `__aenter__`)
- Everything **after `yield`** runs on shutdown (like `__aexit__`)

FastAPI's `lifespan` parameter expects exactly this shape — an async context manager that wraps the application's lifetime.

#### How the three lines work

```python
task = asyncio.create_task(cleanup_loop())  # 1
yield                                        # 2
task.cancel()                                # 3
```

1. **`asyncio.create_task(cleanup_loop())`** — schedules `cleanup_loop()` as a background coroutine on the event loop. It starts running concurrently alongside request handling. The returned `task` object is a handle we can use to cancel it later.

2. **`yield`** — pauses the lifespan generator and hands control to FastAPI. The app is now running and serving requests. The generator stays suspended here for the entire lifetime of the server. The cleanup task is running in the background during this time.

3. **`task.cancel()`** — when the server shuts down (Ctrl+C, etc.), FastAPI resumes the generator past `yield`. We cancel the background task so it doesn't keep running (or throw errors) during shutdown. This raises `asyncio.CancelledError` inside the sleeping `cleanup_loop`, which terminates it cleanly.

### Route parameter renaming

Routes that accept both a request body and the FastAPI `Request` object needed their body parameter renamed to avoid shadowing. For example:

```python
# Before:
async def new_game(request: NewGameRequest | None = None):

# After:
async def new_game(request: Request, response: Response, game_request: NewGameRequest | None = None):
```

FastAPI distinguishes these by type — it knows `Request` and `Response` are special framework objects (injected automatically), while `NewGameRequest` is a Pydantic model (parsed from the request body).

### Stats route fix

The `/api/stats/{player_name}` route previously used `session.tracker.get_player_stats()`, which meant it was tied to whatever session happened to exist. Since stats are global (stored in SQLite), it now creates a standalone `GameTracker()` that reads directly from the database without needing any particular session.

---

## Frontend Change: `game.js`

One line added in `restoreOrStartGame()`:

```javascript
elements.settingsModal.classList.add('hidden');
```

The settings modal starts visible in the HTML. When starting a *new* game, `newGame()` hides it. But when *restoring* an existing game on page refresh, we skip `newGame()` and go straight to `renderGameState()` — so the modal was staying visible on top of the restored game. This line hides it.
