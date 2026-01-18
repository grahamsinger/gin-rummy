# Gin Rummy - Future Enhancements

---
## Active TODOs
---

## Bugs
(none currently)

## AI Tuning
- [ ] Tune ContextAwareAI parameters (currently ~55% win rate vs BasicAI)
  - Best config so far: threshold=3, key_out=2, denial=0
  - See SIMULATION_HISTORY.md for detailed results
- [x] Investigate opponent modeling
  - Implemented via Opponent Meld Inference (see below)

### ContextAwareAI Improvement Roadmap
- [x] **Opponent Meld Inference** (High Impact)
  - Track specific cards opponent picks up, not just rank/suit frequencies
  - Infer likely melds: if opponent picks 7♥ then 8♥ → likely building hearts run
  - Generate "danger cards" list: cards that would complete opponent's inferred melds
  - Use danger cards in discard decisions (danger_card_penalty config)
- [ ] **Deadwood-Based Discard Safety** (Medium Impact)
  - Factor card deadwood value into safety calculation
  - High cards (K, Q, J) safer early game (less meld potential)
  - Low cards riskier (more combinations possible)
- [ ] **Knock Timing Strategy** (Medium Impact)
  - Gin pursuit: if deadwood 1-3, consider holding for gin bonus
  - Opponent deadwood estimation based on their pick/discard patterns
  - If opponent likely has high deadwood → knock early
- [ ] **Discard Pile Sequence Memory** (Low-Medium Impact)
  - Weight recent discards higher than old ones
  - Track discard order to infer hand evolution
  - If opponent discarded X early but picked related cards later, X might be wanted now
- [ ] **End-Game Desperation Mode** (Low Impact)
  - When deck < 5 cards: dramatically lower all thresholds
  - Take any card that reduces deadwood
  - Knock immediately when able
- [ ] **Fix Denial Bonus** (Low Impact)
  - Current denial bonus hurts performance (predictions inaccurate)
  - Only apply when confidence high (2+ pickups of same rank)
  - Or remove entirely and focus on own hand optimization
- [x] AI difficulty levels (easy/medium/hard)
  - Implemented in web UI settings modal
  - Easy (BasicAI), Medium (ContextAwareAI), Hard (ContextAwareAI)
- [x] StatisticalAI implementation
  - Tracks win rates for draw/discard/knock decisions
  - Uses probabilistic selection weighted by historical outcomes
  - Currently underperforms vs heuristic AIs (needs better training approach)
- [x] AI tournament/comparison framework
  - Round-robin results in docs/ai-tournament.md
  - Ranking: ContextAwareAI > BasicAI >> StatisticalAI

## Simulator Improvements
- [x] Add game ending breakdown to simulation results (COMPLETED)
  - Shows % of rounds ending by: knock, gin, undercut, draw
  - Added pts-per-knock-win and pts-per-undercut metrics
- [x] Support per-player config overrides (COMPLETED)
  - CLI: `--ai1-config`, `--ai2-config`, `--ai1-type`, `--ai2-type`
  - Override files in `config/overrides/`
  - See `config/overrides/README.md` for usage

## Learning AI (Reinforcement Learning) - IMPLEMENTED
- [x] Create LearningAI as third AI type (alongside BasicAI, ContextAwareAI)
  - Uses Deep Q-Learning with PyTorch
  - Three separate networks: DrawNet, DiscardNet, KnockNet
- [x] State representation design (~200 features)
  - Hand encoding (52-dim one-hot)
  - Dead cards encoding (52-dim multi-hot)
  - Discard top encoding (52-dim one-hot)
  - Opponent patterns (34-dim: pickup/discard by rank/suit)
  - Game features (8-dim: deck position, deadwood, score, etc.)
- [x] Action space
  - Draw decision (2 outputs: deck vs discard)
  - Discard selection (11 outputs: one per card position)
  - Knock decision (2 outputs: don't knock vs knock)
- [x] Reward function
  - End of round: +50 gin, +20 knock, +30 undercut, -points/5 for loss
  - Intermediate: +0.1 per deadwood reduction, +1.0 per meld completed
- [x] Model persistence
  - Save/load via `ModelPersistence` class
  - Checkpoints with metadata (episode, exploration rate)
- [x] Training infrastructure
  - `Trainer` class with full training loop
  - Experience replay buffer (per decision type)
  - Target network for stable training
  - Curriculum learning: BasicAI -> ContextAwareAI -> self-play
  - TensorBoard logging support
- [x] Evaluation metrics
  - Periodic evaluation against BasicAI
  - Win rate and avg points tracking
  - Training metrics logging
- [x] Integration
  - `--ai1-type learning` / `--ai2-type learning` in simulator
  - `--ai1-model` / `--ai2-model` to specify trained model
  - `gin-train` command for training: `uv run gin-train --episodes 10000`
  - Optional dependency: `uv sync --extra learning`

### Training the Learning AI
```bash
# Install learning dependencies
uv sync --extra learning

# Train a new model
uv run gin-train --episodes 10000 --output models/learning_ai.pt

# Monitor training with TensorBoard
tensorboard --logdir runs/

# Use trained model in simulation
uv run gin-simulate --ai1-type learning --ai1-model models/learning_ai.pt --ai2-type context
```

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
- [x] Statistics dashboard/summary command
  - Lifetime stats tracking in SQLite (player_stats table)
  - Web UI stats modal with 14 statistics
  - API endpoint `/api/stats/{player_name}`

## Laying Off (COMPLETED)
- [x] Allow defender to lay off cards on knocker's melds after knock
  - Implemented `can_lay_off_on_meld()` for runs and sets
  - Implemented `find_layoff_cards()` with chain layoff support
  - Implemented `calculate_deadwood_after_layoff()`
- [x] Update scoring to account for laid off cards
  - `knock()` now uses laying off when knocker has deadwood > 0
  - No laying off allowed on gin (knocker deadwood = 0)

## UI Improvements
- [x] **PRIORITY: Highlight drawn card in hand display**
  - Make it MUCH CLEARER which card was just drawn
  - Implemented: Card is now 15% bigger with bright pulsing yellow glow
  - Persists until player discards
  - Maintains size when hovered or selected
- [x] **Score History Display**
  - Show round-by-round score progression for current game
  - Display who won each round and points awarded
  - Accessible via button or modal in web UI
  - Shows badges for GIN, UNDERCUT, and DRAW outcomes
  - Filters out incomplete rounds in progress
- [x] **Player Management & Stats Control**
  - Store all past players in a dropdown or searchable list
  - Allow viewing stats for any previously played player
  - Allow clearing stats for the current player
  - Clearing stats must be confirmed with a confirmation dialog to avoid accidental deletion
- [ ] **Player Selection in New Game Modal**
  - Add dropdown/autocomplete to select from existing players when starting a new game
  - Show player list with their stats (e.g., "Sarah (7 hands, 86% wins)")
  - Allow typing a new name or selecting an existing player
  - Pre-fill last used player name by default
  - Makes it easy to switch between players without retyping names
- [ ] **Web UI: Manual card arrangement (drag & drop)**
  - Allow players to manually reorder cards in their hand via drag and drop
  - Use HTML5 drag and drop API (no library needed)
  - Should work alongside existing sort buttons (suit/rank/value)
  - Add "Reset" button to return to last sort mode
  - See docs/web_ui_spec.md for detailed implementation notes

## Game Variants & Modes
- [ ] **Oklahoma Gin / Match Play Format**
  - **Game Format Options:**
    - Match Play: Best of 3 games ("3 streets"), first to win 2 games wins
    - Total Points: Single continuous game to target score (e.g., 250, 500 points)
  - **Rules Options (toggleable):**
    - Standard Gin: Fixed knock threshold (10 deadwood)
    - Oklahoma Gin Rules: Upcard determines knock threshold
      - **IMPORTANT: Different dealing procedure:**
        - Deal 10 cards to EACH player (not 11 to one, 10 to the other)
        - Turn over next card as upcard (determines knock threshold)
        - Non-dealer goes first
        - No initial discard phase
      - Ace upcard: Must gin (0 deadwood required)
      - 2-10 upcard: Can knock with that value or less
      - J/Q/K upcard: Can knock with 10 or less (standard)
      - Spade upcard: All points doubled for that hand
  - Settings modal should allow selecting format and rules variant
  - **Implementation Note:** Will need to refactor deal() to support both dealing modes
- [ ] Tournament mode with multiple rounds/scoring
- [ ] Undo last move (within same turn)

---
## Completed
---

## Web UI (COMPLETED)
- [x] FastAPI-based web interface
- [x] Real-time game play against AI
- [x] Settings modal for player name and AI difficulty
- [x] Statistics viewer for lifetime stats
- [x] Card tracker and assist mode
- [x] Responsive design with card animations
- [x] Knock checkbox for better UX (no more prompts)
- [x] Custom player name support throughout UI
- [x] Layoff display with suit symbols

## Bug Fix: AI Pickup-Then-Discard (COMPLETED)
- [x] **FIXED: AI picking up card and immediately discarding it**
  - Root cause: `decide_draw` and `decide_discard` were not coordinated
  - `_card_helps_hand` used simple deadwood simulation, but `decide_discard` (especially in ContextAwareAI) used additional scoring factors (safety, danger, live outs)
  - This mismatch caused AI to think a card helps, then discard it immediately
  - **Fix**: Modified `_card_helps_hand` to call `self.decide_discard()` to see what would ACTUALLY be discarded
  - Added explicit check: reject taking card if we would immediately discard it
  - Added regression test `test_never_pickup_and_immediately_discard` with 100 random scenarios
  - Verified with simulation: no infinite loops, normal discard pile pickup rates

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
