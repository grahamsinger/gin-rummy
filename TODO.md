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

## Unified Card Location Tracking
- [ ] Create `KnownCards` data structure to track all cards from player's perspective
  - `MY_HAND`: Cards in my hand
  - `OPPONENT_HAND_KNOWN`: Cards opponent picked from discard (and hasn't re-discarded)
  - `DISCARD_TOP`: Top of discard pile (available to take)
    should this be named "DISCARD_FACE_DOWN" instead??
  - `DISCARD_BURIED`: Previously discarded, now buried
  - `UNKNOWN`: In deck or opponent's initial hand (can't distinguish)
- [ ] Fix bug: `dead_cards` should include opponent pickups
  - Currently: `dead_cards = set(discard_history)`
  - Should be: `dead_cards = set(discard_history) | (opponent_pickups - re-discarded)`
  - Cards opponent picked up are NOT available to draw!
- [ ] Add helper method to derive location for any card
  - `get_card_location(card) -> CardLocation`
  - Useful for debugging and analysis
- [ ] Update outs analysis to use corrected dead_cards
- [ ] Add to analyze_hand.py output
  - Show card location breakdown
  - "Known opponent cards: X, Unknown cards: Y"

## Card Helpfulness Ranking
- [ ] Rank all non-dead cards by how helpful they would be
  - Primary metric: deadwood reduction when added to hand
  - For each unknown card, calculate: current_deadwood - deadwood_with_card
  - Higher reduction = more helpful
- [ ] Track "helpful cards remaining" count
  - How many live (non-dead) cards would improve the hand
  - Weighted by degree of helpfulness
- [ ] Integrate into outs analysis
  - Current outs focus on meld-completing; this is broader (any improvement)
  - Could replace or complement existing partial_outs
- [ ] Add to analyze_hand.py tool output
  - Show ranked list of helpful cards with deadwood reduction values
  - Show summary: "X helpful cards remaining (Y known dead)"
- [ ] Use in AI decision-making
  - Better context for draw decisions (how many good cards are left?)
  - Late game: few helpful cards = more desperate = lower threshold

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
