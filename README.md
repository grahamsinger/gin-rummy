# Gin Rummy

A terminal-based Gin Rummy card game for two players.

## Installation

```bash
cd gin
uv sync
```

## How to Play

```bash
uv run gin-rummy
```

## Game Rules

### Setup
- Each player is dealt 10 cards
- Non-dealer receives an 11th card and must discard one to start the discard pile
- Non-dealer takes the first turn

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

### Round End
- A player knocks, OR
- Deck reduced to 2 cards = **draw** (no points)

## Controls

| Input | Action |
|-------|--------|
| `1` | Draw from deck |
| `2` | Draw from discard pile |
| `D` | Discard a card |
| `K` | Knock (when available) |
| `q` | Quit game |

When selecting a card to discard, enter the card number shown (1-11).

## Example Session

```
==================================================
              GIN RUMMY
==================================================

Scores: Alice: 0  |  Bob: 0

Bob has 10 cards
Deck: 31 cards
Discard pile: 7♥

Alice's hand (deadwood: 47):
   1. A♣   2. 3♦   3. 5♦   4. 7♠   5. 8♠
   6. 9♥   7. 10♣  8. J♦   9. Q♥  10. K♠

Draw from:
  [1] Deck
  [2] Discard pile (7♥)

Your choice:
```

## Running Tests

```bash
uv run pytest
```

## AI Simulator

Run AI vs AI games to test strategies and collect metrics:

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

Example output:

```
============================================================
SIMULATION RESULTS
============================================================
Games played: 100
Total rounds: 1203
Draws (deck exhausted): 3

Metric                                 AI 1         AI 2
------------------------------------------------------------
Games won                                52           48
Rounds won                              598          602
Total points                           8234         8456
Gins                                      4            2
Knocks                                  602          598
Avg knock deadwood                      3.4          3.2
Undercuts made                           98          102
Undercuts received                      102           98
Draws from deck                        7012         7198
Draws from discard                     2456         2234
Discard draw rate                    25.9%       23.7%
============================================================
```

## AI Development

### Logging AI Decisions

The AI logs its reasoning at different verbosity levels:

```bash
# In tests
uv run pytest tests/test_ai.py --log-cli-level=INFO

# In simulator
uv run gin-simulate -n 5 -v
```

Example log output:

```
gin_rummy.ai - INFO - Draw decision: DISCARD - taking 7♣ (reduces deadwood from 25 to 18 by discarding K♣)
gin_rummy.ai - INFO - Discard decision: K♣ (leaves deadwood=18, best of 11 options)
gin_rummy.ai - INFO - Knock decision: YES (deadwood=6 <= 10, basic strategy: always knock when able)
```

### Programmatic Simulation

```python
from gin_rummy.simulator import run_simulation, Simulator, SimulatorConfig
from gin_rummy.ai import BasicAI

# Quick simulation
metrics = run_simulation(num_games=100, seed=42)
print(metrics.summary())

# With custom AIs
class AggressiveAI(BasicAI):
    """Knocks as soon as possible."""
    pass

class CautiousAI(BasicAI):
    """Waits for lower deadwood before knocking."""
    def should_knock(self, hand):
        return hand.deadwood_total <= 5  # More conservative

ai1 = AggressiveAI()
ai2 = CautiousAI()

config = SimulatorConfig(num_games=100, target_score=100, seed=42)
simulator = Simulator(ai1=ai1, ai2=ai2, config=config)
metrics = simulator.run()

print(f"Aggressive wins: {metrics.player1.games_won}")
print(f"Cautious wins: {metrics.player2.games_won}")
```

### Metrics Available

| Metric | Description |
|--------|-------------|
| `games_won` | Total games won |
| `rounds_won` | Total rounds won |
| `total_points` | Cumulative points scored |
| `gins` | Number of gins (0 deadwood) |
| `knocks` | Total knocks |
| `avg_knock_deadwood` | Average deadwood when knocking |
| `undercuts_made` | Times opponent was undercut |
| `undercuts_received` | Times undercut by opponent |
| `draws_from_deck` | Cards drawn from deck |
| `draws_from_discard` | Cards drawn from discard |
| `discard_draw_rate` | % of draws from discard pile |

## Type Checking

```bash
uv run ty check
```
