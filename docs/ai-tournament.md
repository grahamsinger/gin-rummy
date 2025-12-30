# AI Tournament Results

Round-robin tournament between all available AI implementations.

**Date:** 2025-12-30
**Games per matchup:** 100
**Seed:** 42 (for reproducibility)

## Summary

| Rank | AI | Wins | Losses | Win Rate | Rounds Won | Total Points |
|------|-----|------|--------|----------|------------|--------------|
| 1 | **ContextAwareAI** | 141 | 59 | 70.5% | 997 | 19,096 |
| 2 | BasicAI | 130 | 70 | 65.0% | 979 | 18,206 |
| 3 | StatisticalAI | 29 | 171 | 14.5% | 586 | 9,821 |

## Head-to-Head Results

### BasicAI vs ContextAwareAI

A very close matchup - the two heuristic-based AIs perform nearly identically.

| Metric | BasicAI | ContextAwareAI |
|--------|---------|----------------|
| **Games Won** | 48 | 52 |
| Rounds Won | 460 | 461 |
| Total Points | 7,810 | 8,324 |
| Gins | 13 | 7 |
| Avg Knock Deadwood | 7.1 | 7.1 |
| Discard Draw Rate | 25.1% | 15.8% |

**Observation:** Nearly even. BasicAI draws from discard more aggressively (25% vs 16%), but ContextAwareAI's safer play yields slightly better results.

---

### BasicAI vs StatisticalAI

BasicAI dominates the StatisticalAI decisively.

| Metric | BasicAI | StatisticalAI |
|--------|---------|---------------|
| **Games Won** | 82 | 18 |
| Rounds Won | 519 | 307 |
| Total Points | 10,396 | 5,458 |
| Gins | 12 | 8 |
| Avg Knock Deadwood | 7.0 | 7.0 |
| Discard Draw Rate | 16.1% | 33.0% |

**Observation:** StatisticalAI draws from discard twice as often (33% vs 16%), suggesting its learned statistics are encouraging over-aggressive discard pile usage that doesn't translate to wins.

---

### ContextAwareAI vs StatisticalAI

ContextAwareAI wins even more decisively.

| Metric | ContextAwareAI | StatisticalAI |
|--------|----------------|---------------|
| **Games Won** | 89 | 11 |
| Rounds Won | 536 | 279 |
| Total Points | 10,772 | 4,363 |
| Gins | 8 | 4 |
| Avg Knock Deadwood | 6.9 | 7.3 |
| Discard Draw Rate | 11.2% | 32.1% |

**Observation:** ContextAwareAI's conservative discard draw rate (11%) and lower knock deadwood (6.9) outperform StatisticalAI's aggressive approach.

---

## AI Descriptions

### 1. ContextAwareAI (Best)
Extends BasicAI with game-state awareness:
- Dynamic draw thresholds based on deck position and outs
- Opponent pattern tracking (safe/dangerous ranks and suits)
- Meld-completing card detection with bonuses
- Denial play (taking cards opponent wants)

### 2. BasicAI (Middle)
Simple heuristic-based AI:
- Takes from discard if card reduces deadwood by configurable threshold
- Discards highest deadwood card not in melds
- Knocks based on strategy ("always" or "conservative")

### 3. StatisticalAI (Worst - Currently)
Learning-based AI that tracks action outcomes:
- Records win rates for draw decisions by deadwood bucket
- Tracks which card discards lead to wins/losses
- Uses probabilistic selection weighted by historical win rates
- Falls back to BasicAI when insufficient data

**Why is StatisticalAI underperforming?**
- Currently learning from self-play, which may reinforce suboptimal patterns
- High discard draw rate (32-33%) suggests learned statistics overvalue taking from discard
- Probabilistic selection adds variance that may hurt consistency
- May need more training data or learning from stronger opponents

---

## Conclusions

1. **ContextAwareAI is the strongest** - its game-state awareness and opponent modeling provide a meaningful edge over pure heuristics.

2. **BasicAI is surprisingly competitive** - simple, well-tuned heuristics perform nearly as well as the context-aware version.

3. **StatisticalAI needs improvement** - the current learned statistics are leading to suboptimal play, particularly over-aggressive discard pile usage. Consider:
   - Training against stronger opponents (ContextAwareAI)
   - Resetting statistics and relearning
   - Adjusting the probabilistic selection temperature
   - Adding more sophisticated features to the statistics
