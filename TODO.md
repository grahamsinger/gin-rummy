# Gin Rummy - Future Enhancements

---
## Active TODOs
---

## AI Tuning
- [ ] Tune ContextAwareAI parameters (currently ~53% win rate vs BasicAI)
  - Best config so far: threshold=3, key_out=2, denial=0
  - See SIMULATION_HISTORY.md for detailed results
- [ ] Investigate opponent modeling
  - How are we determining if a card might be helpful for opponent?
  - Current OpponentModel tracks pickup/discard patterns by rank/suit
  - Denial bonus was hurting performance - predictions may be inaccurate
  - Consider: track which melds opponent might be building based on pickups
- [ ] AI difficulty levels (easy/medium/hard)

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

## Game Tracking
- [ ] Game history/replay viewer
- [ ] Statistics dashboard/summary command

## Laying Off
- [ ] Allow defender to lay off cards on knocker's melds after knock
- [ ] Update scoring to account for laid off cards

## UI Improvements
- [ ] Highlight the card just drawn in the hand display
  - Make it easier to identify which card was added to hand
  - Options: bold, underline, background color, or marker (e.g., asterisk/arrow)

## Future Ideas
- [ ] Web UI version
- [ ] Oklahoma Gin variant (variable knock threshold)
- [ ] Tournament mode with multiple rounds/scoring
- [ ] Undo last move (within same turn)

---
## Completed
---

## Meld Detection (COMPLETED)
- [x] Implement run detection (3+ consecutive cards of same suit)
- [x] Implement set detection (3-4 cards of same rank)
- [x] Calculate optimal deadwood (minimize unmelded card values)
- [x] Handle overlapping meld possibilities (choose best combination)

## AI Opponent (COMPLETED - Basic)
- [x] Basic AI with meld-aware strategy
- [x] ContextAwareAI that tracks discards, outs, and opponent patterns

## Unified Card Location Tracking (COMPLETED)
- [x] Create `KnownCards` data structure to track all cards from player's perspective
- [x] Fix bug: `dead_cards` should include opponent pickups
- [x] Add helper method to derive location for any card
- [x] Update outs analysis to use corrected dead_cards
- [x] Add to analyze_hand.py output

## Game Tracking - SQLite (COMPLETED)
- [x] SQLite database for game/hand/turn history
- [x] Track statistics across sessions (wins, gins, undercuts)
- [x] AI decision logging for analysis
- [x] Fix: turns table card format (now uses consistent ASCII format)

## Training/Assist Mode (COMPLETED)
- [x] Show cards remaining in deck
- [x] Track cards opponent picked up from discard pile
- [x] Track all "dead" cards (discarded throughout hand)
- [x] Toggle between showing counts vs actual card values
- [x] Config setting + runtime keyboard shortcut ('a')

## UI Improvements (COMPLETED)
- [x] Show melds and deadwood in hand display
- [x] Color output for suits (red hearts/diamonds)
- [x] Suit-row layout with cards positioned by rank
- [x] Brackets around melded cards
- [x] Superscript selection numbers

## Network Multiplayer (COMPLETED)
- [x] Multiplayer over network
  - Server: `uv run gin-server`
  - Client: `uv run gin-client <ip-address>`

## Code Refactor (COMPLETED)
- [x] Extract shared AI turn logic into reusable module (`gin_rummy/game_runner.py`)
- [x] Refactor CLI and Simulator to use shared module

## Configuration Refactor (COMPLETED)
- [x] Split config.toml into separate files by concern
- [x] Updated config.py to load from config/ directory
