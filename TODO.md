# Gin Rummy - Future Enhancements

---
## Active TODOs
---

## Bugs
(from full code review 2026-07-12; IDs referenced in commits/tests — regression tests in `tests/test_review_fixes.py`)

### Still open
- [ ] **A10 (Low): `_should_pursue_gin` EV comparison is vacuous** — `context_aware.py`: `p*25 + (1-p)*ev_knock > ev_knock` holds for any p>0, so only the probability gate matters; gin value should be `25 + opponent_deadwood` and the probability denominator should account for opponent-held unknowns and remaining turns. (Tuning-adjacent; see AI Tuning section.)
- [ ] **T3: `tests/test_learning.py` silently skips** without torch (`--extra learning`), so the learning suite is permanently green-but-unrun in default env. Run it in CI via `uv sync --extra learning`.
- [ ] **T4: Zero coverage on product surfaces** — web/ (0%), network/ (0%), cli.py (0%), simulator/game_runner (0%), statistical.py (14%); overall 29%. Highest-value additions: FastAPI TestClient flow tests, `network/protocol.py` round-trip tests. (Engine draw-game/knock-rejection tests added 2026-07-12.)
- [ ] **Perf (Low): MC draw fallback runs a full nested MC discard evaluation** — `monte_carlo.py` `_card_helps_hand` path invokes MonteCarloAI's own `decide_discard` on the hypothetical 11-card hand, doubling per-turn compute when the fallback triggers.
- [ ] **(Low) Defender meld arrangement vs layoff** — `calculate_layoff` fixes the defender's own melds to the minimal-deadwood arrangement first; a different equal-deadwood arrangement could occasionally enable a bigger layoff. Cards laid off within a fixed arrangement are now optimal (E2), but arrangement choice itself isn't layoff-aware.

### Fixed 2026-07-12
- [x] **E1 (High): "Cannot discard the card just drawn from the discard pile" rule unenforced** — was a stubbed `pass` in `game.py`. Now: `Game` tracks draw source, `discard()` raises, `discard_blocked_card` property exposed; enforced in web session (both discard and knock paths), CLI re-prompts, and `game_runner` substitutes the best legal alternative if an AI picks the blocked card.
- [x] **E2 (High): Defender layoff was greedy and order-dependent** — `find_layoff_cards()` placed each card on the first meld it fit, blocking chain layoffs (verified 4-point overcount). Now searches all placements to maximize laid-off deadwood value.
- [x] **E3 (Medium): `RoundResult.winner_deadwood`/`loser_deadwood` ignored layoffs** — now report the values actually used for scoring (defender post-layoff).
- [x] **E4 (Medium): `Game.knock()` accepted an 11-card knock** — now rejects hands over 10 cards (closes the `/api/game/knock` hole).
- [x] **E5 (Low): Knock paths bypassed `game.discard()` bookkeeping** — added `Game.knock_with_discard(card)`; game_runner, CLI, and web session all use it (discard pile + history + blocked-card rule handled centrally).
- [x] **W1 (High): Human-triggered stock exhaustion soft-locked the round** — `game_session.draw()` now converts a deck draw at ≤ min_deck_cards into a proper draw result (`_end_round_as_draw`, shared with the AI path) with DB `end_hand` recorded.
- [x] **W2 (High): Match state carried into the next match** — a finished match (match_winner set) now resets `games_won`/`match_winner`/`match_id` on "Play Again"; player rename mid-match re-keys the tally instead of KeyError.
- [x] **W3 (Medium): `/api/game/new-round` worked mid-round** — now requires `phase == ROUND_OVER`.
- [x] **W4 (Medium): Page refresh during Computer's turn soft-locked the UI** — session-restore path now kicks `doAiTurn()` when it's not the player's turn.
- [x] **W5 (Low): Client hardcoded knock threshold 10; server silently downgraded invalid knocks** — client uses `state.knock_threshold`; server returns an explicit error for an illegal knock request instead of quietly discarding.
- [x] **W6 (Low): Server error messages never reached the user** — client now reads FastAPI's `detail` field (falls back to `error`).
- [x] **W7 (Low): `CardNotInHandError` escaped as HTTP 500** — added to the session's except clause; knock path also goes through `knock_with_discard` which validates first.
- [x] **A1 (High): MC "continue" knock rollout gave a phantom extra turn with an empty discard pile** — continue-rollouts now start with the opponent to move and the pending discard on the pile.
- [x] **A2 (High): StatisticalAI recorded phantom discards from hypothetical evaluations** — `_card_helps_hand` marks hypothetical calls (`_in_hypothetical`); StatisticalAI only records real discards.
- [x] **A3 (High): Pending knock-discard leaked into MC unknown pool** — `should_knock(..., pending_discard=)` plumbed through game_runner; the card is excluded from sampling.
- [x] **A4 (Medium): Opponent-held cards counted as live outs** — added `KnownCards.unavailable_cards` (buried + opponent-held); ContextAwareAI outs calculations use it (UI "dead cards" display semantics unchanged).
- [x] **A5 (Medium): "Game-winning knock" shortcut ignored layoffs/undercuts** — removed the unconditional shortcut in ContextAwareAI and MonteCarloAI (game-winning situation remains a strong knock-score bonus; MC sims price undercuts correctly).
- [x] **A6 (Medium): MC rollout deck-exhaustion diverged from engine** — rollout now only ends in a draw on a deck-draw attempt at ≤ min_deck_cards (config value plumbed through).
- [x] **A7 (Low): Knock eligibility hardcoded 10** — BasicAI uses configured `game_rules.knock_threshold`; `GameContext` now carries the live (Oklahoma-dynamic) threshold and ContextAware/MC use it.
- [x] **A8 (Low): OpponentModel never forgot re-discarded pickups** — `record_discard` now un-tracks a thrown-back pickup and recomputes inferred melds.
- [x] **A9 (Low): MC discard tie-break was dead code** — now tie-breaks equal averages toward lower resulting deadwood.
- [x] **T1: `tests/test_4card_run.py` never asserted** — rewritten with real assertions (also fixed its wrong premise: Ace is low, so J-Q-K-A is not a 4-card run).
- [x] **T2: Oklahoma spade doubling was unverified** — deterministic gin scenario asserts exact 2× points on spade upcard, 1× on non-spade or doubling-disabled.
- [x] **E6: Buried discards included the player's own pickups** — `get_game_context()` subtracted opponent pickups from `discard_buried` but not the player's own, so a card you took from the pile stayed listed as "dead" in assist data (CLI + web). Found via the scenario quiz; fixed and regression-tested.

### Rule gaps (variants — decide if in scope)
- [ ] **Big gin not implemented** — an 11-card all-melded hand cannot be declared; player must discard (and standard big-gin bonus doesn't exist in config).
- [ ] **First-upcard take-or-pass not implemented** — standard gin offers the upcard to non-dealer then dealer before stock draws begin; this codebase uses the documented 11th-card variant instead (README) and Oklahoma mode deals an upcard but skips the take-or-pass phase.

## AI Tuning
- [x] **MonteCarloAI upgrades (2026-07-12)** — three improvements, each behind a config flag in `config/monte-carlo-ai.toml` (tests in `tests/test_mc_upgrades.py`):
  - `weighted_sampling`: opponent-hand sampling weighted by observed behavior (discards make related cards less likely, pickups/inferred melds more likely) instead of uniform
  - `defensive_rollout`: rollout discards avoid cards that immediately meld into the (determinized) opposing hand, within 2 deadwood of the greedy choice
  - `joint_turn_evaluation`: each candidate discard is scored against both "knock now" and "continue" with shared samples; the (discard, knock) pair is planned jointly and `should_knock` consumes the plan
  - A/B benchmark configs: `config/overrides/mc-bench-new.toml` vs `mc-bench-legacy.toml` (identical sims, flags on/off)
  - [x] Benchmark results recorded in SIMULATION_HISTORY.md (2026-07-12 section): upgrades beat legacy 12-8 head-to-head; full-strength MC edges ContextAwareAI 9-6; latency grid in experiments/mc_timing.py
  - [ ] MC latency optimizations for web play: sub-batch splitting (draw caps at 2 parallel tasks), top-5 discard candidate cap, adaptive early stopping; consider a 500-sim "web hard" profile (~4.4s/turn vs ~19s at 2000)
- [ ] Tune ContextAwareAI parameters (currently ~52% game win rate, ~46% hand win rate vs BasicAI)
  - Wins fewer hands but wins bigger (more gins, more undercuts, higher pts/knock)
  - See SIMULATION_HISTORY.md for detailed results
- [ ] Investigate ContextAwareAI knock timing behavior
  - AI appears to knock almost immediately when deadwood drops below threshold (10 points)
  - **Knocking should not be binary**: Just because you CAN knock doesn't mean you SHOULD knock
  - Human strategic considerations:
    - Risk assessment: How likely is opponent to undercut? (based on their discard patterns)
    - Opportunity cost: Is it worth waiting to improve position vs locking in current advantage?
    - Deck depletion: More urgency to knock as deck runs low (fewer chances to improve)
    - Score situation: Behind in score → more aggressive knocking; ahead → can be more selective
    - Gin pursuit vs safe knock: Don't ALWAYS pursue gin/lower deadwood if knock is safe now
    - Example: Knocking with 7 deadwood might be better than waiting for 5 if opponent looks strong
  - Identify which config parameters control knock timing/eagerness
  - Evaluate if immediate knocking is optimal or if waiting for better opportunities would improve win rate
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
- [x] Rank all non-dead cards by how helpful they would be (WEB UI)
  - Primary metric: deadwood reduction when added to hand
  - Simulates full draw-and-discard cycle for accurate helpfulness
  - Shows top 10 most helpful cards with reduction values
  - Dead cards shown with strikethrough
- [x] Track "helpful cards remaining" count (WEB UI)
  - Shows live (available) and dead (unavailable) helpful cards count
  - Integrated into assist info panel
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
- [x] **Hand Replay Viewer** (COMPLETED)
  - Turn tracking added to web game session (game_session.py)
  - Deferred DB creation: game/hand records only created when human makes first move
  - AI turns buffered and flushed when human plays
  - API endpoint: `GET /api/hands/{hand_id}/turns`
  - API endpoint: `GET /api/history` for browsing all past games
  - Score History modal: click any hand to view turn-by-turn replay
  - History Explorer page (`/history`): browse and filter all past games
  - Replay component with keyboard navigation (arrows, home/end, escape)
  - Admin cleanup endpoint to remove abandoned games with no turn data
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
- [x] **Standardize Button Sizes** (COMPLETED)
  - Footer control buttons standardized (padding, font-size, border-radius)
  - "Explore History" renamed to "Archive"
- [ ] **Show Dealer Indicator**
  - Display who is the dealer for the current hand
  - Useful for verifying game logic (dealer alternates each round)
  - Could show "DEALER" badge next to player/computer name
  - Helps understand turn order in Oklahoma Gin (non-dealer goes first)
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
- [x] **Player Selection in New Game Modal**
  - Add dropdown/autocomplete to select from existing players when starting a new game
  - Show player list with their stats (e.g., "Sarah (7 hands, 86% wins)")
  - Allow typing a new name or selecting an existing player
  - Pre-fill last used player name by default (as placeholder)
  - Filter out "Computer" from player list and prevent using it as name
  - Added Cancel button to close modal without starting game
- [x] **Fix Game Over Modal Flow - Show Round Result First**
  - **FIXED:** Removed early return that skipped round result modal
  - Now shows round result modal first, then game over modal after clicking "Next Round"
  - Flow: Round ends → Show round result → User clicks "Next Round" → Check if game over → Show game over modal
  - Backend: AI action is now always set before checking round result type
  - Frontend: nextRound() checks if game is over before starting new round
- [x] **Show Computer's Final Move in Round Result Modal**
  - **FIXED:** Computer's last action now shown in round result modal
  - Displays: "Computer drew [from deck/discard pile] and discarded [card]"
  - Only shown when computer wins (not when human wins or draw)
  - Backend fix: AI action is set even when AI knocks/gins
  - Frontend: Added AI action display to showRoundResult() function
- [ ] **Web UI: Manual card arrangement (drag & drop)**
  - Allow players to manually reorder cards in their hand via drag and drop
  - Use HTML5 drag and drop API (no library needed)
  - Should work alongside existing sort buttons (suit/rank/value)
  - Add "Reset" button to return to last sort mode
  - See docs/web_ui_spec.md for detailed implementation notes
- [x] **History Viewer: Display hands like player view** (COMPLETED)
  - Melds grouped together with colored backgrounds (blue for runs, purple for sets)
  - Deadwood cards sorted by rank (highest first)
  - Applied to both "Hand Before" and "Hand After" displays
  - API analyzes cards using `analyze_hand` and returns meld info
- [x] **History Viewer: Deadwood progression graph** (COMPLETED)
  - SVG line graph showing deadwood over time for both players
  - X-axis: turn number, Y-axis: deadwood value
  - Two lines: player (blue) and computer (red)
  - Current turn highlighted with yellow ring
  - Legend showing player names
  - Pure SVG implementation (no external libraries)
- [x] **History Viewer: Filter by player** (COMPLETED)
  - Filter buttons: "All", player name, "Computer"
  - Navigation (arrows/first/last) skips filtered-out turns
  - Filtered-out turns shown dimmed in turn list
  - Position display updates to show filtered count
- [x] **History Viewer: Show deadwood in turn list** (COMPLETED)
  - Deadwood value shown in parentheses next to player name
  - Format: "1 | Computer (24) | 8♠ → J♣"
  - Allows quick scanning of deadwood progression

## Game Variants & Modes
- [x] **Oklahoma Gin / Match Play Format** (COMPLETED)
  - **Game Format Options:**
    - Match Play: Best of 3 games, first to win 2 games wins
    - Total Points: Single continuous game to target score (e.g., 100, 150, 200, 250 points)
  - **Rules Options (toggleable):**
    - Standard Gin: Fixed knock threshold (10 deadwood)
    - Oklahoma Gin Rules: Upcard determines knock threshold
      - Deal 10 cards to EACH player (not 11 to one, 10 to the other)
      - Turn over next card as upcard (determines knock threshold)
      - Non-dealer goes first
      - No initial discard phase
      - Ace upcard: Must gin (0 deadwood required)
      - 2-10 upcard: Can knock with that value or less
      - J/Q/K upcard: Can knock with 10 or less (standard)
      - Spade upcard: All points doubled for that hand
  - Settings modal with checkboxes for Oklahoma Gin, Spade Doubling, and Match Play
  - UI displays knock threshold and spade doubling indicator when applicable
  - Match progress tracking shows games won (e.g., "You 1 - 0 Computer")
- [x] **Scenario quiz (`gin-scenario` + web `/scenario` page)** — random mid-game positions (generated by freezing real AI-vs-AI hands, so discard history and opponent tracking are genuine); you play draw/discard/knock, then each AI reveals its choice with reasoning and MC EVs; agreement scoreboard per session. CLI: `uv run gin-scenario [--count N] [--seed S]`. Web: `/scenario` page (endpoints in app.py, `ScenarioSession` in web/scenario_session.py, tests in tests/test_scenario_session.py); page restores in-progress scenario on reload.
  - [ ] Possible follow-up: "grade my games" mode replaying recorded human turns from the DB through the AI panel
- [x] **Shared card display constants (`card-utils.js`)** — suit symbols/colors were defined independently in game.js, replay.js, memory.js, and scenario.js; now a single `window.CardUtils` module loaded by all four pages.
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
