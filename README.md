# Gin Rummy

A terminal-based Gin Rummy card game for two players.

## Installation

```bash
cd gin
uv sync
```

## How to Play

```bash
uv run gin-rummy
```

## Game Rules

### Setup
- Each player is dealt 10 cards
- Non-dealer receives an 11th card and must discard one to start the discard pile
- Non-dealer takes the first turn

### Turn Structure
1. **Draw**: Take one card from either:
   - `[1]` The deck (face down)
   - `[2]` The discard pile (face up, top card visible)

2. **Discard or Knock**:
   - `[D]` Discard a card to end your turn
   - `[K]` Knock (only available when deadwood ≤ 10)

### Deadwood & Melds
- **Melds** are sets (3-4 of same rank) or runs (3+ consecutive same suit)
- **Deadwood** = total value of unmelded cards
- Card values: Ace=1, Face cards=10, Others=face value

### Knocking
- You may knock when your deadwood is **10 or less**
- **Gin** (0 deadwood): 25 points + opponent's deadwood
- **Undercut** (opponent has ≤ your deadwood): Opponent gets 25 points + difference

### Round End
- A player knocks, OR
- Deck reduced to 2 cards = **draw** (no points)

## Controls

| Input | Action |
|-------|--------|
| `1` | Draw from deck |
| `2` | Draw from discard pile |
| `D` | Discard a card |
| `K` | Knock (when available) |
| `q` | Quit game |

When selecting a card to discard, enter the card number shown (1-11).

## Example Session

```
==================================================
              GIN RUMMY
==================================================

Scores: Alice: 0  |  Bob: 0

Bob has 10 cards
Deck: 31 cards
Discard pile: 7♥

Alice's hand (deadwood: 47):
   1. A♣   2. 3♦   3. 5♦   4. 7♠   5. 8♠
   6. 9♥   7. 10♣  8. J♦   9. Q♥  10. K♠

Draw from:
  [1] Deck
  [2] Discard pile (7♥)

Your choice:
```

## Running Tests

```bash
uv run pytest
```

## AI Simulator

Run AI vs AI games to test strategies and collect metrics:

```bash
# Run 100 games with default settings
uv run gin-simulate

# Run 50 games with a fixed seed (reproducible)
uv run gin-simulate -n 50 -s 42

# With AI decision logging
uv run gin-simulate -v

# See all options
uv run gin-simulate --help
```

Example output (shows AI class names for easy comparison):

```
==============================================================
SIMULATION RESULTS
==============================================================
Games played: 100
Total rounds: 1203
Draws (deck exhausted): 3

Metric                         AI 1 (BasicAI) AI 2 (BasicAI)
--------------------------------------------------------------
Games won                                  52             48
Rounds won                                598            602
Total points                             8234           8456
Gins                                        4              2
Knocks                                    602            598
Avg knock deadwood                        3.4            3.2
Undercuts made                             98            102
...
==============================================================
```

For custom AI development, programmatic usage, and detailed metrics, see [docs/ai-simulation.md](docs/ai-simulation.md).

## Web UI

Play in your browser with a visual interface:

```bash
uv run uvicorn gin_rummy.web.app:app --reload
```

Then open http://127.0.0.1:8000

Click cards to draw/discard, no typing required.

## Type Checking

```bash
uv run ty check
```
