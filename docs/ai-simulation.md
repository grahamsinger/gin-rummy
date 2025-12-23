# AI Simulation Guide

Run AI vs AI games to test strategies, compare implementations, and collect performance metrics.

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

# See all options
uv run gin-simulate --help
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `-n, --num-games` | 100 | Number of games to simulate |
| `-t, --target-score` | 100 | Score needed to win a game (0 for single-round mode) |
| `-s, --seed` | None | Random seed for reproducibility |
| `-v, --verbose` | 0 | Increase verbosity (-v for INFO, -vv for DEBUG) |
| `--max-rounds` | 50 | Maximum rounds per game (safety limit) |

## Example Output

The simulator now shows the AI class name for each player, making it easy to compare different implementations:

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
Undercuts received                        102             98
Draws from deck                          7012           7198
Draws from discard                       2456           2234
Discard draw rate                       25.9%         23.7%
==============================================================
```

When comparing different AI classes:

```
==============================================================================
SIMULATION RESULTS
==============================================================================
Games played: 100
Total rounds: 1156
Draws (deck exhausted): 5

Metric                         AI 1 (AggressiveAI) AI 2 (ConservativeAI)
------------------------------------------------------------------------------
Games won                                       61                    39
...
```

## Programmatic Usage

### Basic Simulation

```python
from gin_rummy.simulator import run_simulation, Simulator, SimulatorConfig
from gin_rummy.ai import BasicAI

# Quick simulation with defaults
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
    """Knocks as soon as legally possible."""

    def should_knock(self, hand):
        # Always knock when deadwood <= 10
        return hand.deadwood_total <= 10


class ConservativeAI(BasicAI):
    """Only knocks with very low deadwood."""

    def should_knock(self, hand):
        # Wait for deadwood <= 3 before knocking
        return hand.deadwood_total <= 3


# Run comparison
config = SimulatorConfig(num_games=100, target_score=100, seed=42)
simulator = Simulator(ai1=AggressiveAI(), ai2=ConservativeAI(), config=config)
metrics = simulator.run()

print(metrics.summary())
print(f"\nAggressive wins: {metrics.player1.games_won}")
print(f"Conservative wins: {metrics.player2.games_won}")
```

## Creating Custom AIs

The `BasicAI` class provides several methods you can override to customize behavior:

### Overridable Methods

#### `decide_draw(hand, discard_top) -> DrawChoice`

Decide whether to draw from the deck or discard pile.

```python
from gin_rummy.ai import BasicAI, DrawChoice

class AlwaysDrawFromDeck(BasicAI):
    """Never picks up from discard pile."""

    def decide_draw(self, hand, discard_top):
        return DrawChoice.DECK


class GreedyDiscard(BasicAI):
    """Takes from discard pile if it helps at all."""

    def __init__(self):
        super().__init__()
        self.min_deadwood_improvement = 0  # Take any helpful card
```

**Parameters:**
- `hand`: Current hand (10 cards)
- `discard_top`: Top card of discard pile, or `None` if empty

**Returns:** `DrawChoice.DECK` or `DrawChoice.DISCARD`

---

#### `decide_discard(hand) -> Card`

Decide which card to discard after drawing.

```python
class DiscardHighest(BasicAI):
    """Always discards the highest deadwood value card."""

    def decide_discard(self, hand):
        return max(hand, key=lambda c: c.deadwood_value)


class DiscardRandom(BasicAI):
    """Discards a random card."""

    def decide_discard(self, hand):
        import random
        return random.choice(list(hand))
```

**Parameters:**
- `hand`: Current hand (11 cards after drawing)

**Returns:** `Card` to discard

---

#### `should_knock(hand) -> bool`

Decide whether to knock (when legally allowed).

```python
class NeverKnock(BasicAI):
    """Only goes gin, never knocks."""

    def should_knock(self, hand):
        return hand.deadwood_total == 0  # Only gin


class KnockAt5(BasicAI):
    """Knocks when deadwood is 5 or less."""

    def should_knock(self, hand):
        return hand.deadwood_total <= 5
```

**Parameters:**
- `hand`: Current hand (10 cards)

**Returns:** `True` to knock, `False` to continue

---

#### `make_turn_decision(hand, discard_top, drawn_card) -> tuple[Card, bool]`

Combined decision for discard and knock after drawing. Override this for more complex logic that considers both together.

```python
class SmartKnock(BasicAI):
    """Considers what to discard before deciding to knock."""

    def make_turn_decision(self, hand, discard_top, drawn_card):
        # Find best discard
        discard = self.decide_discard(hand)

        # Calculate post-discard deadwood
        from gin_rummy.melds import analyze_hand
        remaining = [c for c in hand if c != discard]
        post_deadwood = analyze_hand(remaining).deadwood_value

        # Custom knock logic based on situation
        should_knock = post_deadwood <= 5 or (post_deadwood <= 8 and len(hand) < 5)

        return discard, should_knock
```

**Parameters:**
- `hand`: Current hand (11 cards after drawing)
- `discard_top`: What was on top of discard pile (for context)
- `drawn_card`: The card that was just drawn

**Returns:** Tuple of `(card_to_discard, should_knock)`

---

### Internal Helper Method

#### `_card_helps_hand(hand, card) -> tuple[bool, str]`

Check if picking up a card would help the hand. Override for custom evaluation.

```python
class SetFocused(BasicAI):
    """Prioritizes building sets over runs."""

    def _card_helps_hand(self, hand, card):
        # Check if card matches rank of any card in hand
        matching_ranks = sum(1 for c in hand if c.rank == card.rank)

        if matching_ranks >= 2:
            return True, f"completes set of {card.rank.name}s"
        elif matching_ranks == 1:
            return True, f"pairs with existing {card.rank.name}"

        # Fall back to default logic
        return super()._card_helps_hand(hand, card)
```

**Parameters:**
- `hand`: Current hand
- `card`: Card to evaluate

**Returns:** Tuple of `(helps: bool, reason: str)`

## Configuration via TOML

The default `BasicAI` reads settings from `config.toml`:

```toml
[ai]
# When to knock: "always" or "conservative"
knock_strategy = "always"

# When conservative, only knock at this threshold
conservative_knock_threshold = 5

# Minimum deadwood improvement to take from discard
min_deadwood_improvement = 1
```

Custom AIs can override these in their `__init__`:

```python
class VeryConservative(BasicAI):
    def __init__(self):
        super().__init__()
        self.knock_strategy = "conservative"
        self.conservative_knock_threshold = 3
        self.min_deadwood_improvement = 2
```

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

## Logging AI Decisions

Enable verbose logging to see AI reasoning:

```bash
# In simulator
uv run gin-simulate -n 5 -v

# In tests
uv run pytest tests/test_ai.py --log-cli-level=INFO
```

Example log output:

```
gin_rummy.ai - INFO - Draw decision: DISCARD - taking 7♣ (reduces deadwood from 25 to 18 by discarding K♣)
gin_rummy.ai - INFO - Discard decision: K♣ (leaves deadwood=18, best of 11 options)
gin_rummy.ai - INFO - Knock decision: YES (deadwood=6, strategy=always)
```

For even more detail:

```bash
uv run gin-simulate -n 5 -vv
```

```
gin_rummy.ai - DEBUG - Draw decision: current hand ['A♣', '3♦', '5♦', ...] (deadwood=47)
gin_rummy.ai - DEBUG - Discard options (card -> resulting deadwood): [('K♠', 18), ('Q♥', 22), ...]
```
