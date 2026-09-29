# Gin Rummy Codebase Reading Order

Recommended order for understanding this codebase. Each layer builds on the previous.

## Layer 1: Data Models (Foundation) - `models/`

1. **`models/card.py`** - Start here. Defines `Suit`, `Rank`, and `Card`. Immutable dataclass with deadwood values and comparison operators.

2. **`models/deck.py`** - Simple collection of Cards with shuffle/draw operations.

3. **`models/hand.py`** - A player's hand of Cards. Has caching for meld analysis.

4. **`models/melds.py`** - Core gin rummy logic: sets, runs, and optimal deadwood calculation. The `find_optimal_melds()` function uses recursive backtracking to find the best non-overlapping meld combination.

5. **`models/player.py`** - Thin wrapper: name + hand + score.

## Layer 2: Configuration

6. **`config.py`** - Dataclass-based config with TOML loading. Defines game rules, AI behavior, display settings, etc. Most modules import `get_config()` from here.

## Layer 3: Game State

7. **`game.py`** - The state machine. Handles game phases (DEALING, DRAWING, DISCARDING, etc.), enforces rules, tracks discard history. The `Game` class is where gin rummy rules are implemented.

## Layer 4: AI System

8. **`models/game_context.py`** and **`models/outs.py`** - What an AI decides from: `GameContext` (a snapshot of the game from one seat), `KnownCards` / `CardLocation` (where every card is), and the outs dataclasses.

9. **`ai/`** - The AI players and their support code:
   - `ai/basic.py` - `BasicAI`, the interface every AI shares (draw, discard, knock, each with a `*_with_reasoning` twin) and the simplest heuristic
   - `ai/context_aware.py` - Extends BasicAI with dynamic thresholds, outs analysis and opponent modelling
   - `ai/outs.py`, `ai/opponent_model.py`, `ai/thresholds.py` - The heuristics ContextAwareAI is built from
   - `ai/statistical.py`, `ai/mc/` (Monte Carlo rollouts), `learning/` (neural) - The other AIs
   - `ai/factory.py` - `make_ai("basic" | "context" | ...)`

## Layer 5: Execution

10. **`game_runner.py`** - One AI turn: `execute_ai_turn()` draws, discards and maybe knocks, returning the actions. Every caller uses it.

11. **`round_runner.py`** - One round: `run_round(game, seats)` plays the opening discard and turns until a knock or the deck runs out, relaying each player's actions to the other seat. A `Seat` is a human prompt or an AI. The CLI, simulator, scenario quiz and trainer are seats over it; the web session stays request-driven.

## Layer 6: Entry Points / Applications

12. **`cli/`** - Terminal interface for human vs AI or player vs player. `render.py` draws the table, `prompts.py` reads input, `round.py` holds the seats, `app.py` is `main`.

13. **`simulator/`** - AI vs AI with metrics collection (`runner.py`, `metrics.py`, `cli.py`). Good for testing AI changes; `scripts/fingerprint.py` builds on it.

14. **`db/`** - SQLite game history: `schema.py`, `migrations.py`, `connection.py`, `tracker.py` (`GameTracker` records games as they are played), `queries.py` (the read side). `tracking.py` turns a turn's actions into the rows the tracker stores.

15. **`web/`** - The FastAPI app (`app.py`), one `GameSession` per browser session, and the scenario quiz session.

16. **`analyze_hand.py`** - CLI utility to analyze a hand's outs. Usage: `uv run python -m gin_rummy.analyze_hand "3S 8S 2H..."`

## Dependency Graph (simplified)

```
models/
  card --> deck
    |
    +-> hand --> melds
          |
          +-> player --> game --> models/game_context --> ai/
                           |                              |
                           +------------------------------+-> game_runner --> round_runner
                                                                    |              |
                                                               web/ (turns)   cli/ simulator/ scenario/ learning/trainer
                                                                    |              |
                                                                    +------ db/ ---+
```
