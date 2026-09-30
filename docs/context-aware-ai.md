# ContextAwareAI

A smarter AI that adjusts its drawing decisions based on game context, rather than using fixed thresholds.

## How It Differs from BasicAI

### BasicAI Behavior
BasicAI uses a simple, static rule for drawing:
- Take from discard if it reduces deadwood by at least `min_deadwood_improvement` (default: 1)
- This threshold never changes regardless of game state

### ContextAwareAI Behavior
ContextAwareAI dynamically adjusts its draw threshold based on:

1. **Deck Position** - Late game = lower threshold (more desperate to improve)
2. **Outs Count** - Many "outs" = higher threshold (can afford to wait for better cards)
3. **Score Differential** - Trailing badly = lower threshold (need to take risks)
4. **Key Outs** - Meld-completing cards get a bonus (worth taking even below threshold)
5. **Denial Play** - Cards opponent wants get a bonus (deny them the card)

---

## GameContext: What Gets Captured

The `GameContext` dataclass is a snapshot of the game state passed to the AI each turn. Here's what it contains:

| Field | Type | Description |
|-------|------|-------------|
| `deck_remaining` | `int` | Number of cards left in the deck (starts at ~31 after deal) |
| `deck_position_pct` | `float` | 0.0 = full deck, 1.0 = nearly empty. Used for game phase detection |
| `discard_history` | `list[Card]` | All cards discarded this hand (oldest first) |
| `opponent_pickups` | `list[Card]` | Cards opponent has taken from discard pile |
| `my_pickups` | `list[Card]` | Cards I have taken from discard pile |
| `dead_cards` | `set[Card]` | Buried discards (cards in discard pile that can't be drawn) |
| `my_score` | `int` | My current game score |
| `opponent_score` | `int` | Opponent's current game score |
| `target_score` | `int` | Points needed to win (default: 100) |
| `my_outs` | `OutsAnalysis \| None` | Calculated outs for my hand (set by AI during decision) |

### Computed Properties

| Property | Type | Description |
|----------|------|-------------|
| `score_differential` | `int` | `my_score - opponent_score`. Positive = leading |
| `points_to_win` | `int` | How many more points I need |
| `opponent_points_to_win` | `int` | How many more points opponent needs |

---

## Core Concepts

### Outs
An "out" is a card that would help your hand. There are two types:

**Meld-completing outs** (weight: 10.0)
- Cards that complete a set or run
- Example: You have 7♥ 8♥, so 6♥ and 9♥ are meld-completing outs

**Partial outs** (weight: 4-5)
- Cards that build toward melds
- Example: You have a pair of 5s, so the other two 5s are partial outs
- Weighted higher in early game, nearly worthless in late game

### Dead Cards
Cards in the discard pile that are buried (can't be drawn):
- Does NOT include the top of the discard pile (that's available to draw)
- Does NOT include opponent's known cards (tracked separately)
- Used to mark outs as "dead" (unavailable)

### Opponent Model
Tracks what opponent discards and picks up to predict:
- `predict_will_discard(card)` - Probability they'll discard this card
- `predict_will_take(card)` - Probability they'd take this card

Used for "denial play" - taking a card the opponent likely wants.

---

## The Dynamic Threshold Formula

```
threshold = base + deck_modifier + outs_modifier + score_modifier

Where:
- base = 1 (configurable)
- deck_modifier = -2.0 * deck_position_pct (0 to -2)
- outs_modifier = min(live_outs / 10, 2.0) (0 to 2)
- score_modifier = -2 if trailing badly, +1 if leading comfortably
```

**Example scenarios:**

| Situation | Threshold | Meaning |
|-----------|-----------|---------|
| Early game, even score, few outs | ~1 | Normal selectivity |
| Late game, trailing by 60 pts | ~0 | Take anything that helps |
| Early game, leading, many outs | ~3-4 | Be very selective |

---

## Configuration Reference

All parameters are in `config/context-ai.toml` under `[context_aware_ai]` (a single `config.toml` is only the fallback when there is no `config/` directory). Here's the complete reference with types, defaults, and tuning guidance:

### Base Threshold

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_draw_threshold` | `int` | `1` | Starting threshold before modifiers |

**Tuning:**
- Increase to `2` or `3` if AI takes too many cards from discard
- Decrease to `0` if AI is too conservative

```toml
# More conservative baseline
base_draw_threshold = 2
```

---

### Outs Calculation Weights

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `meld_completing_weight` | `float` | `10.0` | Weight for cards that complete a 3+ card meld |
| `run_extending_weight` | `float` | `5.0` | Weight for cards that extend a 2-card run sequence |
| `set_building_weight` | `float` | `4.0` | Weight for cards that extend a pair toward a set |
| `partial_meld_early_bonus` | `float` | `2.0` | Multiplier for partial outs in early game |

**Tuning:**
- `meld_completing_weight`: Keep high (8-12). These are the most valuable outs.
- `run_extending_weight`: Reduce if AI overvalues potential runs. Try `3.0`.
- `set_building_weight`: Reduce if AI chases sets too much. Try `2.0`.
- `partial_meld_early_bonus`: Reduce to `1.0` if AI is too aggressive early.

```toml
# Less aggressive toward partial melds
run_extending_weight = 3.0
set_building_weight = 2.0
partial_meld_early_bonus = 1.0
```

---

### Game Phase Boundaries

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `early_game_threshold` | `float` | `0.7` | Deck > 70% remaining = early game |
| `late_game_threshold` | `float` | `0.3` | Deck < 30% remaining = late game |

**Tuning:**
- Affects when partial outs get bonus/penalty
- Increase `late_game_threshold` to `0.4` if AI should focus on melds earlier

```toml
# Treat more of the game as "late" phase
late_game_threshold = 0.4
```

---

### Threshold Modifiers

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_deck_modifier` | `float` | `2.0` | Maximum threshold reduction in late game |
| `max_outs_modifier` | `float` | `2.0` | Maximum threshold increase from having many outs |
| `trailing_aggressive_threshold` | `int` | `50` | Points behind to trigger aggressive play |
| `leading_conservative_threshold` | `int` | `30` | Points ahead to trigger conservative play |

**Tuning:**
- `max_deck_modifier`: Reduce to `1.0` if AI takes too many cards late game
- `max_outs_modifier`: Reduce if AI waits too long when it has many outs
- `trailing_aggressive_threshold`: Increase to `70` if AI should stay calm when behind
- `leading_conservative_threshold`: Decrease to `20` if AI should stay aggressive when ahead

```toml
# More moderate adjustments
max_deck_modifier = 1.0
max_outs_modifier = 1.5
trailing_aggressive_threshold = 40
```

---

### Bonus Adjustments

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `denial_bonus` | `int` | `2` | Added when opponent likely wants the card |
| `denial_probability_threshold` | `float` | `0.7` | Opponent want probability to trigger denial bonus |

**Tuning:**
- `denial_bonus`: **Likely needs reduction**. Try `1` or `0`. Current value may cause AI to take cards just to deny opponent.
- `denial_probability_threshold`: Increase to `0.8` or `0.9` to make denial less frequent.

```toml
# More conservative bonuses (recommended for tuning)
denial_bonus = 1
denial_probability_threshold = 0.8
```

---

### Opponent Modeling

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `near_meld_patience` | `int` | `2` | Draws a pair or two-card run is given to fill before it is thrown as deadwood (0 = lowest deadwood only). Measured against BasicAI over 2000 games: 0 wins 53%, 2 wins 65%, 6 wins 54% |
| `track_opponent_patterns` | `bool` | `true` | Whether to track opponent discard/pickup patterns |

**Tuning:**
- Set to `false` to disable opponent modeling entirely
- Useful for A/B testing the impact of denial play

```toml
# Disable opponent tracking
track_opponent_patterns = false
```

---

## Current Status: Needs Tuning

The ContextAwareAI framework is complete but currently underperforms BasicAI:

```
Games played: 200
ContextAwareAI wins: 81 (40.5%)
BasicAI wins: 119 (59.5%)
```

**Why it's losing:**

The AI is taking from the discard pile much more often (54% vs 18%), but those cards aren't actually helping enough. The current parameters are too aggressive - it's picking up cards that look helpful but don't actually reduce deadwood sufficiently.

**Recommended starting point for tuning:**

```toml
[context_aware_ai]
# Start with a higher baseline
base_draw_threshold = 2

# Reduce bonuses significantly
denial_bonus = 1

# Make denial harder to trigger
denial_probability_threshold = 0.85

# Reduce partial out values
run_extending_weight = 3.0
set_building_weight = 2.0
partial_meld_early_bonus = 1.0

# Reduce late-game desperation
max_deck_modifier = 1.5
```

---

## Running Comparison Simulations

```python
from gin_rummy.simulator import Simulator, SimulatorConfig
from gin_rummy.ai import BasicAI, ContextAwareAI

config = SimulatorConfig(num_games=500, seed=42)
sim = Simulator(ai1=ContextAwareAI(), ai2=BasicAI(), config=config)
metrics = sim.run()
print(metrics.summary())

# Key metrics to watch:
# - Win rate (target: >50%, ideally >55%)
# - Discard draw rate (currently too high at 54%)
# - Undercuts made vs received
```

---

## Architecture

```
ContextAwareAI (extends BasicAI)
├── OutsCalculator
│   └── Finds meld-completing and partial outs
├── OpponentModel
│   └── Tracks patterns, predicts behavior
└── DynamicThresholdCalculator
    └── Computes threshold from game context

Game.get_game_context(player_idx)
└── Builds GameContext snapshot for AI
```

---

## Files

| File | Purpose |
|------|---------|
| `gin_rummy/models/game_context.py`, `models/outs.py` | GameContext, KnownCards, OutsAnalysis (domain data) |
| `gin_rummy/ai/outs.py`, `ai/opponent_model.py`, `ai/thresholds.py` | OutsCalculator, OpponentModel, DynamicThresholdCalculator (heuristics) |
| `gin_rummy/ai/context_aware.py` | ContextAwareAI class (extends BasicAI) |
| `gin_rummy/game.py` | get_game_context() method |
| `gin_rummy/config.py` | ContextAwareAIConfig dataclass |
| `tests/test_context.py` | Unit tests for context components |
