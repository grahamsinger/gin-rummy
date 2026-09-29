# Gin Rummy

A Gin Rummy card game with a web UI and a terminal interface, AI opponents at several strengths, an AI-vs-AI simulator, a scenario quiz that grades your play against the AIs, and a reinforcement-learning AI.

## Installation

```bash
cd gin
uv sync              # game, CLI, simulator
uv sync --extra web  # + FastAPI web UI
uv sync --extra learning  # + PyTorch for the learning AI
```

## Web UI

```bash
uv run uvicorn gin_rummy.web.app:app --reload
```

Then open http://127.0.0.1:8000

| Page | What it is |
|------|------------|
| `/` | Play against the AI |
| `/history` | Browse every recorded game and replay any hand turn by turn |
| `/scenario` | Scenario quiz: play a real mid-game position, then see what each AI would have done and why |
| `/memory` | Card memory game |

### Features

- **AI Difficulty**: Easy (BasicAI), Medium (ContextAwareAI) or Hard (MonteCarloAI)
- **Game Modes**: Practice (endless hands) or Target Score (100/150/200/250 points)
- **Oklahoma Gin**: Upcard determines knock threshold, spade doubling optional
- **Match Play**: Best of 3 games
- **Statistics**: Lifetime stats per player (wins, gins, undercuts, ...)
- **Score History**: Round-by-round results; click any round to replay it
- **Hand Replay**: Step through any completed hand, with the AI's reasoning for each decision
- **Assist Mode**: Card tracker showing dead cards, opponent pickups and helpful cards

Each browser gets its own session (cookie), and games are recorded to `game_history.db` (see `config/database.toml`).

## Terminal UI

```bash
uv run gin-rummy      # human vs AI, or player vs player
uv run gin-scenario   # scenario quiz in the terminal (--count N --seed S)
```

## Game Rules

### Setup
- Each player is dealt 10 cards
- Non-dealer receives an 11th card and must discard one to start the discard pile
- Dealer then draws, and discards first

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
- The defender may lay off cards on the knocker's melds (not on gin)

### Round End
- A player knocks, OR
- Deck reduced to 2 cards = **draw** (no points)

## Terminal Controls

| Input | Action |
|-------|--------|
| `1` | Draw from deck |
| `2` | Draw from discard pile |
| `D` | Discard a card |
| `K` | Knock (when available) |
| `a` | Assist mode: toggle between card counts and the actual cards |
| `q` | Quit game |

When selecting a card to discard, enter the card number shown (1-11).

## AI Simulator

Run AI vs AI games to test strategies and collect metrics:

```bash
uv run gin-simulate                                   # 100 games, context vs basic
uv run gin-simulate --ai1-type montecarlo --ai2-type context
uv run gin-simulate -n 50 -s 42                       # fixed seed, reproducible
uv run gin-simulate --ai1-config config/overrides/gin_hunter.toml
uv run gin-simulate -v                                # log AI decisions
uv run gin-simulate --help
```

**AI types** (`--ai1-type` / `--ai2-type`):

| Type | Class | Strategy |
|------|-------|----------|
| `basic` | `BasicAI` | Deadwood heuristics; the interface every AI shares |
| `context` | `ContextAwareAI` | Dynamic thresholds, outs analysis, opponent meld inference, danger cards |
| `statistical` | `StatisticalAI` | Picks by recorded win rates (`models/statistical_ai.json`) |
| `montecarlo` | `MonteCarloAI` | Samples opponent hands and rolls out each option in a worker pool |
| `learning` | `LearningAI` | Deep Q-Learning networks (needs `--extra learning` and `--ai1-model`) |

Per-player config overrides live in `config/overrides/` (see its README). Results of past runs are in [SIMULATION_HISTORY.md](SIMULATION_HISTORY.md); custom AIs, programmatic use and the metrics are in [docs/ai-simulation.md](docs/ai-simulation.md).

## Learning AI (Experimental)

```bash
uv sync --extra learning
uv run gin-train --episodes 10000 --output models/my_model.pt   # train
uv run gin-experiment --preset fast --name trial-1              # hyperparameter experiments
uv run gin-simulate --ai1-type learning --ai1-model models/my_model.pt
```

See [docs/learning-ai.md](docs/learning-ai.md) for the architecture and training tips.

## Configuration

Settings are TOML files in `config/` (game rules, each AI, display, database and logging), merged at startup. Override files for simulations only contain the values they change.

## Development

```bash
uv run pytest                        # tests
uv run ruff check . && uv run ruff format --check .
npm run lint                         # eslint for the web frontend
uv run ty check                      # type checking
uv run python scripts/fingerprint.py # behaviour fingerprint for refactors (docs/fingerprinting.md)
uvx pre-commit install               # ruff on every commit
```

Analyse a hand's melds and outs from the shell: `uv run python -m gin_rummy.analyze_hand "3S 8S 2H ..."` ([docs/analyze-hand.md](docs/analyze-hand.md)).

## Documentation

| Document | Contents |
|----------|----------|
| [docs/reading-order.md](docs/reading-order.md) | Where to start reading the code, layer by layer |
| [docs/ai-simulation.md](docs/ai-simulation.md) | Simulator CLI, custom AIs, metrics |
| [docs/context-aware-ai.md](docs/context-aware-ai.md) | How ContextAwareAI uses game context |
| [docs/learning-ai.md](docs/learning-ai.md) | The Deep Q-Learning AI and its training loop |
| [docs/fingerprinting.md](docs/fingerprinting.md) | How behaviour-preserving refactors are verified |
| [SIMULATION_HISTORY.md](SIMULATION_HISTORY.md) | AI-vs-AI results over time |
| [TODO.md](TODO.md) | Open work |
| [AUDIT.md](AUDIT.md) | The 2026-09 codebase audit and its review log |
| `docs/archive/` | Design notes that describe earlier layouts of the code |
