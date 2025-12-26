# Simulation History

Historical results from ContextAwareAI vs BasicAI simulations, tracking the impact of configuration changes.

## Current Best Configuration

```toml
[context_aware_ai]
base_draw_threshold = 3
key_out_bonus = 2
denial_bonus = 0
```

**Win Rate: 53.3%** (533/1000 games across 5 seeds)

## Results Log

### 2025-12-26: Parameter Tuning Session

**Goal:** Improve ContextAwareAI win rate from ~40% baseline

#### Baseline (original settings)
- `base_draw_threshold = 1`
- `key_out_bonus = 3`
- `denial_bonus = 2`
- Games: 200 (seed=42)
- **Result: 41.5% win rate** (83-117)
- Discard draw rate: 51.8%
- Notes: AI was too aggressive picking from discard pile

#### Tweak 1: Increase base_draw_threshold to 2
- `base_draw_threshold = 2`
- Games: 200 (seed=42)
- **Result: 46.5% win rate** (93-107)
- Discard draw rate: 32.8%
- Notes: +5% improvement, more selective about pickups

#### Tweak 2: Reduce key_out_bonus to 2
- `base_draw_threshold = 2`, `key_out_bonus = 2`
- Games: 200 (seed=42)
- **Result: 50.0% win rate** (100-100)
- Notes: Additional +3.5% improvement

#### Tweak 3: Increase base_draw_threshold to 3
- `base_draw_threshold = 3`, `key_out_bonus = 2`
- Games: 1000 (5 seeds)
- **Result: 50.0% win rate** (500-500)
- Notes: More consistent results (46.5%-53.5% range vs 38.5%-52% before)

#### Tweak 4: Disable denial_bonus
- `base_draw_threshold = 3`, `key_out_bonus = 2`, `denial_bonus = 0`
- Games: 1000 (5 seeds)
- **Result: 53.3% win rate** (533-467)
- Notes: Opponent model predictions may be inaccurate, causing bad denial pickups

#### Tweak 5: Reduce key_out_bonus to 1
- `base_draw_threshold = 3`, `key_out_bonus = 1`, `denial_bonus = 0`
- Games: 1000 (5 seeds)
- **Result: 52.0% win rate** (520-480)
- Notes: Slightly worse, reverted to key_out_bonus = 2

#### Tweak 6: Conservative knock strategy
- Changed `[ai] knock_strategy = "conservative"` (threshold 5)
- Games: 1000 (5 seeds)
- **Result: 50.7% win rate** (507-493)
- Notes: Hurt performance. Both AIs share [ai] config, so no advantage gained.

#### Final Multi-seed Validation (Best Config)
| Seed | Games | ContextAwareAI | BasicAI | Win Rate |
|------|-------|----------------|---------|----------|
| 42 | 200 | 108 | 92 | 54.0% |
| 123 | 200 | 111 | 89 | 55.5% |
| 456 | 200 | 105 | 95 | 52.5% |
| 789 | 200 | 97 | 103 | 48.5% |
| 1000 | 200 | 112 | 88 | 56.0% |
| **Total** | **1000** | **533** | **467** | **53.3%** |

## Key Insights

1. **Original AI was too aggressive** - 51.8% discard pickup rate was revealing info and taking suboptimal cards
2. **Higher threshold helps** - Forcing more selective pickups improved win rate
3. **Denial bonus hurts** - OpponentModel predictions aren't accurate enough; taking cards just to deny opponent backfired
4. **Knock strategy is shared** - Both AIs use same [ai] config, so changing knock behavior affects both equally

## Next Steps to Improve Further

1. **Add context-aware knock logic to ContextAwareAI**
   - Override `should_knock()` to consider game context
   - Go for gin when ahead, knock early when behind
   - Consider opponent's likely hand strength

2. **Improve opponent modeling**
   - Track which melds opponent might be building
   - Better prediction of what cards help opponent
   - Re-enable denial bonus once predictions are accurate

3. **Dynamic threshold based on hand quality**
   - Lower threshold when hand is already strong
   - Higher threshold when hand needs significant improvement
