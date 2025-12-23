# Gin Rummy - Future Enhancements

## Meld Detection (COMPLETED)
- [x] Implement run detection (3+ consecutive cards of same suit)
- [x] Implement set detection (3-4 cards of same rank)
- [x] Calculate optimal deadwood (minimize unmelded card values)
- [x] Handle overlapping meld possibilities (choose best combination)

## AI Opponent (COMPLETED - Basic)
- [x] Basic AI with meld-aware strategy
- [x] ContextAwareAI that tracks discards, outs, and opponent patterns
- [ ] Tune ContextAwareAI parameters (currently 40.5% win rate vs BasicAI)
  - See docs/context-aware-ai.md for recommended starting values
- [ ] AI difficulty levels (easy/medium/hard)

## Game Tracking (COMPLETED - SQLite)
- [x] SQLite database for game/hand/turn history
- [x] Track statistics across sessions (wins, gins, undercuts)
- [x] AI decision logging for analysis
- [ ] Game history/replay viewer
- [ ] Statistics dashboard/summary command

## Training/Assist Mode (COMPLETED)
- [x] Show cards remaining in deck
- [x] Track cards opponent picked up from discard pile
- [x] Track all "dead" cards (discarded throughout hand)
- [x] Toggle between showing counts vs actual card values
- [x] Config setting + runtime keyboard shortcut ('a')

## Laying Off
- [ ] Allow defender to lay off cards on knocker's melds after knock
- [ ] Update scoring to account for laid off cards

## UI Improvements (COMPLETED)
- [x] Show melds and deadwood in hand display
- [x] Color output for suits (red hearts/diamonds)
- [x] Suit-row layout with cards positioned by rank
- [x] Brackets around melded cards
- [x] Superscript selection numbers

## Code Refactor: Unify Simulator and CLI Game Logic (COMPLETED)
- [x] Extract shared AI turn logic into reusable module
  - Created `gin_rummy/game_runner.py` with `execute_ai_turn()` as single source of truth
- [x] Create shared functions:
  - `execute_ai_turn(game, ai, other_ai, callbacks)` - handles full AI turn with context
  - `record_opponent_pickup/discard()` - track opponent patterns
  - `get_ai_context()` - build context for ContextAwareAI
- [x] Refactor CLI to use shared module
  - `CLITurnCallbacks` handles UI output and database tracking
- [x] Refactor Simulator to use shared module
  - `SimulatorTurnCallbacks` handles metrics tracking

## Configuration Refactor (COMPLETED)
- [x] Split config.toml into separate files by concern:
  - `config/game.toml` - game rules (knock threshold, bonuses)
  - `config/ai.toml` - BasicAI settings
  - `config/context-ai.toml` - ContextAwareAI parameters
  - `config/display.toml` - UI/display + assist settings
  - `config/database.toml` - database + logging settings
- [x] Updated config.py to load from config/ directory (with single file fallback)

## Future Ideas
- [ ] Multiplayer over network
- [ ] Web UI version
- [ ] Oklahoma Gin variant (variable knock threshold)
- [ ] Tournament mode with multiple rounds/scoring
- [ ] Undo last move (within same turn)
