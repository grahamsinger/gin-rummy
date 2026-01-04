# Gin Rummy Web UI Spec

## Overview

A simple web-based UI for playing Gin Rummy against the AI. No frameworks - just vanilla HTML/CSS/JS on the frontend and FastAPI on the backend.

## Architecture

```
┌─────────────────┐         ┌─────────────────┐
│   Browser       │  HTTP   │   FastAPI       │
│   (HTML/CSS/JS) │ ◄─────► │   Backend       │
└─────────────────┘   JSON  │                 │
                            │  ┌───────────┐  │
                            │  │   Game    │  │
                            │  │   Class   │  │
                            │  └───────────┘  │
                            └─────────────────┘
```

- **Backend**: FastAPI server wrapping the existing `Game` class
- **Frontend**: Single HTML page with inline CSS/JS (or minimal separate files)
- **State**: Server holds game state in memory (single-player, no persistence needed)
- **Communication**: Simple REST endpoints returning JSON

## Backend API

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/game/new` | Start a new game, returns game state |
| GET | `/api/game/state` | Get current game state |
| POST | `/api/game/draw` | Draw a card (from deck or discard) |
| POST | `/api/game/discard` | Discard a card |
| POST | `/api/game/knock` | Knock to end round |
| POST | `/api/game/new-round` | Start next round after one ends |

### Game State Response

```json
{
  "phase": "drawing",
  "your_turn": true,
  "hand": [
    {"rank": "7", "suit": "hearts", "id": "7H"},
    {"rank": "K", "suit": "spades", "id": "KS"},
    ...
  ],
  "melds": [
    {"type": "run", "cards": ["5H", "6H", "7H"]},
    {"type": "set", "cards": ["KS", "KH", "KD"]}
  ],
  "deadwood": 12,
  "deadwood_cards": ["9C", "2D"],
  "discard_top": {"rank": "3", "suit": "clubs", "id": "3C"},
  "deck_remaining": 24,
  "opponent_card_count": 10,
  "scores": {"You": 45, "Computer": 32},
  "can_knock": true,
  "message": "Your turn - draw a card"
}
```

### Action Requests

**Draw:**
```json
{"source": "deck"}  // or "discard"
```

**Discard:**
```json
{"card": "9C"}
```

**Knock:** (no body needed)

### Error Response

```json
{"error": "Cannot draw in discarding phase"}
```

## Frontend Design

### Layout (Single Page)

```
┌────────────────────────────────────────────────────┐
│  GIN RUMMY           You: 45  |  Computer: 32      │
├────────────────────────────────────────────────────┤
│                                                    │
│     ┌────┐  Opponent (10 cards)                    │
│     │░░░░│ ░░░░ ░░░░ ░░░░ ░░░░ ░░░░ ...           │
│     └────┘                                         │
│                                                    │
│     ┌────┐  ┌────┐                                 │
│     │DECK│  │ 3♣ │  ← Discard pile                 │
│     │    │  │    │                                 │
│     └────┘  └────┘                                 │
│                                                    │
│     ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ...        │
│     │ 7♥ │ │ K♠ │ │ 5♦ │ │ 9♣ │ │ 2♦ │            │
│     │    │ │    │ │    │ │    │ │    │            │
│     └────┘ └────┘ └────┘ └────┘ └────┘            │
│     Your hand (melds grouped with brackets)        │
│                                                    │
│  [Status: Your turn - click deck or discard]       │
│                                                    │
│  Deadwood: 12    [KNOCK] (if available)            │
└────────────────────────────────────────────────────┘
```

### Card Rendering

Use Unicode suit symbols (♠♥♦♣) with CSS styling:
- Cards are `<div>` elements with rank and suit
- Red suits (♥♦) colored red
- Clickable cards have hover effect
- Selected card highlighted
- Melded cards visually grouped (bracket or background color)

### Interaction Flow

**Drawing Phase:**
1. Deck and discard pile are clickable (highlighted)
2. Click either to draw
3. Hand cards are not clickable yet

**Discarding Phase:**
1. Deck/discard not clickable
2. Hand cards become clickable
3. Click a card to select it
4. Click again to confirm discard (or click different card)
5. If can knock, show KNOCK button

**AI Turn:**
1. Brief delay (0.5-1s) to simulate thinking
2. Show what AI did: "Computer drew from deck"
3. Show what AI discarded: "Computer discarded 5♣"
4. Auto-transition back to player's drawing phase

**Round End:**
1. Show both hands with melds
2. Show who won and points
3. "Play Next Round" button

## File Structure

```
gin_rummy/
├── web/
│   ├── __init__.py
│   ├── app.py          # FastAPI app and routes
│   ├── game_session.py # Wrapper around Game for web state
│   └── static/
│       ├── index.html  # Single page app
│       ├── style.css   # Card styling
│       └── game.js     # Game interaction logic
```

## Implementation Order

1. **Backend first**: Create FastAPI app with endpoints
   - Start with `/api/game/new` and `/api/game/state`
   - Add action endpoints one by one
   - Test with curl/httpie before building frontend

2. **Basic frontend**: Static HTML showing game state
   - Fetch and display current state
   - Card rendering with CSS

3. **Interactions**: Add click handlers
   - Drawing phase
   - Discarding phase
   - Knock button

4. **AI turns**: Handle AI response and animation

5. **Polish**: Round results, new round, game over

## Dependencies

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
web = ["fastapi", "uvicorn"]
```

Run with:
```bash
uv run uvicorn gin_rummy.web.app:app --reload
```

## Planned Enhancements

### Pre-Game Settings Screen

Before starting a game, show a settings modal:

```
┌─────────────────────────────────────┐
│         NEW GAME                    │
├─────────────────────────────────────┤
│  Your name: [__________]            │
│                                     │
│  AI Difficulty:                     │
│    ○ Easy (StatisticalAI)           │
│    ○ Normal (BasicAI)               │
│    ● Hard (ContextAwareAI)          │
│                                     │
│  [Start Game]                       │
└─────────────────────────────────────┘
```

**API change:**
```json
POST /api/game/new
{"player_name": "Alice", "ai_type": "context"}
```

AI types: `"statistical"` (easy), `"basic"` (normal), `"context"` (hard)

### Hand Sorting

Add sort buttons above player's hand:

```
Sort: [By Suit] [By Rank] [By Value]
```

- **By Suit**: Group by suit (♠♥♦♣), then by rank within suit
- **By Rank**: Group by rank (A,2,3...K), then by suit
- **By Value**: Deadwood value descending (K,Q,J,10...A)

This is client-side only - just reorders the display, doesn't affect game state.

**Implementation:**
- Store `sortMode` in JS state
- Re-sort hand array before rendering
- Persist preference in localStorage

### Manual Card Arrangement (Drag & Drop)

Allow player to drag cards to reorder their hand manually.

**Implementation approach:**
- Use HTML5 drag and drop API (no library needed)
- Add `draggable="true"` to card elements
- Track custom order in JS state
- "Reset" button to return to default sort

**Interaction:**
1. Click and hold a card
2. Drag to new position
3. Other cards shift to make room
4. Release to drop

**Considerations:**
- Disable during drawing phase (only allow during discard selection)
- Visual feedback: ghost card, drop indicator
- Touch support: may need additional handling for mobile

### Clearer Opponent Actions

Make it more obvious what the opponent did on their turn:

**Current:** Single status message "Computer drew from deck, discarded 5♣"

**Improved:**
- Separate the draw and discard into two distinct visual moments
- Highlight the discard pile when opponent picks from it
- Show the picked-up card briefly before it "goes to their hand"
- Color-code messages:
  - Green for deck draw (hidden info)
  - Yellow/Orange for discard pickup (they wanted that card!)
- Maybe a brief animation showing card movement

**Message examples:**
- "Computer took 7♥ from discard pile" (highlighted - they wanted it)
- "Computer drew from deck" (neutral)
- "Computer discarded 5♣"

### Command Line AI Selection

Support AI type via uvicorn environment or query param:

```bash
# Environment variable
AI_TYPE=basic uv run uvicorn gin_rummy.web.app:app

# Or default in app, override in settings screen
```

## Open Questions

1. **Card images vs Unicode?**
   - Unicode is simpler (no assets to manage)
   - Images look nicer but add complexity
   - **Recommendation**: Start with Unicode, add images later if desired

2. **Assist mode in web UI?**
   - Show dead cards / opponent known cards?
   - **Recommendation**: Yes, include it - toggle with checkbox

3. **Multiple games?**
   - For now: single game in memory, refresh = new game
   - Later: could add game IDs for multiple sessions

4. **Sound effects?**
   - **Recommendation**: Skip for v1, easy to add later
