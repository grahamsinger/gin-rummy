# AI Simulation Guide

Run AI vs AI games to test strategies, compare implementations, and collect performance metrics.

## Contents

- [Quick Start](#quick-start)
- [CLI Options](#cli-options)
- [Example Output](#example-output)
- [Programmatic Usage](#programmatic-usage)
- [Creating Custom AIs](#creating-custom-ais)
  - [Overridable Methods](#overridable-methods)
  - [Configuration Properties](#configuration-properties)
- [Metrics Reference](#metrics-reference)
- [Logging AI Decisions](#logging-ai-decisions)

---

## Quick Start

```bash
# Run 100 games with default settings
uv run gin-simulate

# Run 50 games with a fixed seed (reproducible)
uv run gin-simulate -n 50 -s 42

# Custom target score (default: 100)
uv run gin-simulate -t 200

# With AI decision logging
uv run gin-simulate -v      # INFO: shows decisions
uv run gin-simulate -vv     # DEBUG: shows all options considered
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `-n, --num-games` | 100 | Number of games to simulate |
| `-t, --target-score` | 100 | Score needed to win a game (0 for single-round mode) |
| `-s, --seed` | None | Random seed for reproducibility |
| `-v, --verbose` | 0 | Increase verbosity (-v for INFO, -vv for DEBUG) |
| `--max-rounds` | 50 | Maximum rounds per game (safety limit) |
| `--ai1-type` | context | AI type for player 1 (basic, context, learning, montecarlo) |
| `--ai2-type` | basic | AI type for player 2 |
| `--mc-sims` | 100 | Number of simulations for Monte Carlo AI |

## Available AI Types

| Type | Class | Description |
|------|-------|-------------|
| `basic` | `BasicAI` | Simple heuristic-based AI |
| `context` | `ContextAwareAI` | Tracks opponent patterns, dynamic thresholds |
| `learning` | `LearningAI` | Neural network trained via DQN (requires model) |
| `statistical` | `StatisticalAI` | Learns from experience over games |

```bash
# Compare different AI types
uv run gin-simulate --ai1-type statistical --ai2-type basic -n 100
uv run gin-simulate --ai1-type context --ai2-type basic -n 100
```

---

## Statistical AI

The `StatisticalAI` learns from experience by tracking outcomes of its decisions over many games.

### How It Works

After each round, the AI records what decisions it made and whether it won or lost. Over time, it builds up statistics about which actions lead to wins.

```
After each round:
    For each decision made this round:
        Update win rate statistics for that action

During decisions:
    If sufficient data exists (20+ samples):
        Use historical win rates to guide choice
    Else:
        Fall back to BasicAI logic
```

### What It Tracks

**1. Card Discard Statistics** (52 entries, one per card):
```json
{
  "card_index": {
    "times": 34,      // times this card was discarded
    "wins": 11,       // rounds won after discarding it
    "points": -118    // net points from those rounds
  }
}
```
- Cards with high win rates when discarded are preferred
- Cards with low win rates are kept longer

**2. Draw Decision Statistics** (by deadwood bucket):
```json
{
  "21-30": {
    "deck_draws": 45,
    "deck_wins": 18,
    "discard_draws": 23,
    "discard_wins": 12
  }
}
```
- Buckets: 0-10, 11-20, 21-30, 31+
- Learns when drawing from discard is beneficial at different deadwood levels

**3. Knock Decision Statistics** (by deadwood value 0-10):
```json
{
  "5": {
    "knocked": 20,
    "knock_wins": 14,
    "continued": 15,
    "continue_wins": 8
  }
}
```
- Learns optimal knock threshold based on outcomes

### Persistence

Statistics are saved to a JSON file after each simulation run:

```bash
# Default location
models/statistical_ai.json

# Custom location
uv run gin-simulate --ai1-type statistical --stats-file my_stats.json -n 100
```

The file is human-readable and can be inspected to see what the AI has learned.

### Usage

```bash
# Train with 100 games (starts from scratch or continues learning)
uv run gin-simulate --ai1-type statistical --ai2-type basic -n 100

# Train more (stats accumulate)
uv run gin-simulate --ai1-type statistical --ai2-type basic -n 500

# Check stats file
cat models/statistical_ai.json | head -50
```

### Learning Curve

The AI improves gradually as it accumulates more data:

| Games Played | Samples | Expected Behavior |
|--------------|---------|-------------------|
| 10 | ~900 | Mostly BasicAI fallback |
| 100 | ~11,000 | Starting to use learned stats |
| 500 | ~55,000 | Most decisions use statistics |
| 1000+ | 100,000+ | Refined strategy based on experience |

### Why Statistical Learning Works

- **Fast**: No simulation overhead, just table lookups
- **Improves over time**: Gets smarter with more games
- **Persistent**: Learning carries across sessions
- **Interpretable**: Can inspect the JSON to see what it learned
- **Adapts**: If you change opponents, it learns new patterns

### Limitations

- **Slow to learn**: Needs many games to build reliable statistics
- **No generalization**: Learns specific cards, not abstract concepts
- **Context-limited**: Doesn't consider game state combinations (e.g., score, deck position)

---

## Example Output

The simulator shows AI class names in the header for easy comparison:

```
==============================================================
SIMULATION RESULTS
==============================================================
Games played: 100
Total rounds: 1203

Metric                         AI 1 (BasicAI) AI 2 (BasicAI)
--------------------------------------------------------------
Games won                                  52             48
Rounds won                                598            602
Gins                                        4              2
Avg knock deadwood                        3.4            3.2
...
==============================================================
```

When comparing different AI implementations:

```
Metric                         AI 1 (AggressiveAI) AI 2 (ConservativeAI)
------------------------------------------------------------------------------
Games won                                       61                    39
```

---

## Programmatic Usage

### Basic Simulation

```python
from gin_rummy.simulator import run_simulation

metrics = run_simulation(num_games=100, seed=42)
print(metrics.summary())

# Access individual metrics
print(f"AI 1 wins: {metrics.player1.games_won}")
print(f"AI 2 wins: {metrics.player2.games_won}")
```

### Comparing Custom AIs

```python
from gin_rummy.simulator import Simulator, SimulatorConfig
from gin_rummy.ai import BasicAI

class AggressiveAI(BasicAI):
    def should_knock(self, hand):
        return hand.deadwood_total <= 10

class ConservativeAI(BasicAI):
    def should_knock(self, hand):
        return hand.deadwood_total <= 3

config = SimulatorConfig(num_games=100, seed=42)
simulator = Simulator(ai1=AggressiveAI(), ai2=ConservativeAI(), config=config)
metrics = simulator.run()

print(metrics.summary())
```

---

## Creating Custom AIs

Subclass `BasicAI` and override methods to customize behavior.

### Overridable Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| [`decide_draw`](#decide_draw) | Choose deck or discard pile | `DrawChoice` |
| [`decide_discard`](#decide_discard) | Choose card to discard | `Card` |
| [`should_knock`](#should_knock) | Decide whether to knock | `bool` |
| [`_card_helps_hand`](#_card_helps_hand) | Evaluate if a card helps | `tuple[bool, str]` |

### Configuration Properties

Set these in `__init__` to adjust the default method implementations *without* overriding them:

| Property | Default | Used By | Description |
|----------|---------|---------|-------------|
| `knock_strategy` | `"always"` | `should_knock()` | See options below |
| `conservative_knock_threshold` | `5` | `should_knock()` | Max deadwood when using `"conservative"` strategy |
| `min_deadwood_improvement` | `1` | `decide_draw()` | Min improvement needed to take from discard |

**`knock_strategy` options:**
- `"always"` - Knock whenever deadwood ≤ 10 (legal threshold)
- `"conservative"` - Only knock when deadwood ≤ `conservative_knock_threshold`

```python
class VeryConservative(BasicAI):
    """Uses the default should_knock() but with tighter thresholds."""
    def __init__(self):
        super().__init__()
        self.knock_strategy = "conservative"
        self.conservative_knock_threshold = 3
        self.min_deadwood_improvement = 2
```

> **Note:** If you override `should_knock()`, your custom logic *replaces* the strategy-based logic entirely - the `knock_strategy` and `conservative_knock_threshold` properties are ignored.

---

## Method Details

### decide_draw

Decide whether to draw from the deck or discard pile.

```python
def decide_draw(self, hand: Hand, discard_top: Card | None) -> DrawChoice
```

**Parameters:**
- `hand` - Current hand (10 cards)
- `discard_top` - Top card of discard pile, or `None` if empty

**Returns:** `DrawChoice.DECK` or `DrawChoice.DISCARD`

**Example:**
```python
from gin_rummy.ai import BasicAI, DrawChoice

class AlwaysDrawFromDeck(BasicAI):
    def decide_draw(self, hand, discard_top):
        return DrawChoice.DECK

class GreedyDiscard(BasicAI):
    def __init__(self):
        super().__init__()
        self.min_deadwood_improvement = 0  # Take any helpful card
```

---

### decide_discard

Decide which card to discard after drawing.

```python
def decide_discard(self, hand: Hand) -> Card
```

**Parameters:**
- `hand` - Current hand (11 cards after drawing)

**Returns:** `Card` to discard

**Example:**
```python
class DiscardHighest(BasicAI):
    def decide_discard(self, hand):
        return max(hand, key=lambda c: c.deadwood_value)

class DiscardRandom(BasicAI):
    def decide_discard(self, hand):
        import random
        return random.choice(list(hand))
```

---

### should_knock

Decide whether to knock (when legally allowed).

```python
def should_knock(self, hand: Hand) -> bool
```

**Parameters:**
- `hand` - Current hand (10 cards)

**Returns:** `True` to knock, `False` to continue

**Default behavior:** Uses `knock_strategy` property (see [Configuration Properties](#configuration-properties)):
- `"always"` → knock when deadwood ≤ 10
- `"conservative"` → knock when deadwood ≤ `conservative_knock_threshold`

**Override examples:**
```python
class NeverKnock(BasicAI):
    """Only goes gin, never knocks."""
    def should_knock(self, hand):
        return hand.deadwood_total == 0  # Ignores knock_strategy

class KnockAt5(BasicAI):
    def should_knock(self, hand):
        return hand.deadwood_total <= 5  # Ignores knock_strategy
```

**Or use config properties without overriding:**
```python
class KnockAt5(BasicAI):
    """Same behavior as above, but using config properties."""
    def __init__(self):
        super().__init__()
        self.knock_strategy = "conservative"
        self.conservative_knock_threshold = 5
```

---

### _card_helps_hand

Check if picking up a card would help the hand. Override for custom evaluation logic.

```python
def _card_helps_hand(self, hand: Hand, card: Card) -> tuple[bool, str]
```

**Parameters:**
- `hand` - Current hand
- `card` - Card to evaluate

**Returns:** Tuple of `(helps: bool, reason: str)`

**Example:**
```python
class SetFocused(BasicAI):
    """Prioritizes building sets over runs."""

    def _card_helps_hand(self, hand, card):
        matching_ranks = sum(1 for c in hand if c.rank == card.rank)

        if matching_ranks >= 2:
            return True, f"completes set of {card.rank.name}s"
        elif matching_ranks == 1:
            return True, f"pairs with existing {card.rank.name}"

        return super()._card_helps_hand(hand, card)
```

---

## Metrics Reference

| Metric | Description |
|--------|-------------|
| `games_won` | Total games won (first to target score) |
| `rounds_won` | Total rounds won |
| `total_points` | Cumulative points scored |
| `gins` | Number of gins (0 deadwood knocks) |
| `knocks` | Total knocks |
| `avg_knock_deadwood` | Average deadwood when knocking |
| `undercuts_made` | Times opponent was undercut |
| `undercuts_received` | Times undercut by opponent |
| `draws_from_deck` | Cards drawn from deck |
| `draws_from_discard` | Cards drawn from discard pile |
| `discard_draw_rate` | Percentage of draws from discard |

---

## Logging AI Decisions

Enable verbose logging to see AI reasoning:

```bash
uv run gin-simulate -n 5 -v
```

```
gin_rummy.ai - INFO - Draw decision: DISCARD - taking 7♣ (reduces deadwood 25 -> 18)
gin_rummy.ai - INFO - Discard decision: K♣ (leaves deadwood=18, best of 11 options)
gin_rummy.ai - INFO - Knock decision: YES (deadwood=6, strategy=always)
```

For even more detail (`-vv`):

```
gin_rummy.ai - DEBUG - Discard options: [('K♠', 18), ('Q♥', 22), ...]
```
