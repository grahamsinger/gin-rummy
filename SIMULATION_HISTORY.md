# Simulation History

Tracking ContextAwareAI vs BasicAI performance across simulation runs.

---

## Phased Knock Strategy Results (2026-02-11)

### Phased Knock vs Flat Knock (Context vs Context A/B test)

| Run | Seed | Games | AI 1 | AI 2 | Wins (AI1-AI2) | Win Rate AI1 |
|-----|------|-------|------|------|----------------|--------------|
| 6   | 42   | 1000  | Phased Knock | Flat Knock | 529-471 | **52.9%** |

| Metric | Phased Knock | Flat Knock |
|--------|-------------|------------|
| Games won | 529 (52.9%) | 471 (47.1%) |
| Rounds won | 4760 | 4662 |
| Total points | 85,390 | 80,025 |
| Gins | 257 | 212 |
| Knocks | 4,629 | 4,793 |
| Avg knock deadwood | 6.3 | 5.9 |
| Pts per knock win | 16.7 | 16.2 |
| Undercuts made | 551 | 420 |
| Pts per undercut | 27.5 | 27.3 |

### Phased Knock Context vs BasicAI

| Run | Seed | Games | AI 1 | AI 2 | Wins (AI1-AI2) | Win Rate AI1 |
|-----|------|-------|------|------|----------------|--------------|
| 7   | 42   | 1000  | Context (Phased) | Basic | 541-459 | **54.1%** |

| Metric | ContextAwareAI (Phased) | BasicAI |
|--------|------------------------|---------|
| Games won | 541 (54.1%) | 459 (45.9%) |
| Rounds won | 4514 | 5076 |
| Total points | 85,666 | 79,002 |
| Gins | 155 | 111 |
| Knocks | 3,978 | 5,612 |
| Avg knock deadwood | 6.6 | 6.8 |
| Pts per knock win | 17.5 | 15.3 |
| Undercuts made | 659 | 123 |
| Pts per undercut | 27.5 | 26.5 |

**Key takeaways (t=100):**
- Phased knock beats flat knock head-to-head: 52.9% win rate
- Phased knock produces 21% more gins (257 vs 212) and 31% more undercuts (551 vs 420)
- vs BasicAI, phased knock improved from ~52% to **54.1%** — a 2 percentage point gain
- Slightly higher avg knock deadwood (6.3 vs 5.9) is expected from early-game aggressive knocking
- The strategy amplifies ContextAwareAI's existing strengths: more gins, more undercuts, higher-value wins

### Higher Target Score Results (target score = 250)

| Run | Seed | Games | Target | AI 1 | AI 2 | Wins (AI1-AI2) | Win Rate AI1 |
|-----|------|-------|--------|------|------|----------------|--------------|
| 8   | 42   | 1000  | 250    | Phased Knock | Flat Knock | 514-486 | **51.4%** |
| 9   | 42   | 1000  | 250    | Context (Phased) | Basic | 545-455 | **54.5%** |
| 10  | random | 1000 | 250   | Phased Knock | Flat Knock | 503-497 | **50.3%** |
| 11  | random | 1000 | 250   | Context (Phased) | Basic | 554-446 | **55.4%** |

### Cross-Target Comparison

| Matchup | t=100 | t=250 (seeded) | t=250 (random) |
|---------|-------|----------------|----------------|
| Phased vs Flat | 52.9% | 51.4% | 50.3% |
| Context vs Basic | 54.1% | 54.5% | 55.4% |

**Key takeaways (t=250):**
- Context vs Basic advantage **increases** with longer games: 54.1% → 54.5-55.4%
- Longer games give ContextAwareAI more opportunities to exploit its quality-over-quantity strategy
- Phased vs Flat edge narrows at t=250 (51.4%/50.3% vs 52.9%), suggesting the early knock bonus matters more in shorter games
- Results are consistent across seeded and random runs, confirming the advantage is not seed-dependent

---

## Baseline Results (2026-02-11)

### Full Games (target score = 100)

| Run | Seed | Games | AI 1 | AI 2 | Wins (AI1-AI2) | Win Rate AI1 |
|-----|------|-------|------|------|----------------|--------------|
| 1   | 42   | 500   | Context | Basic | 260-240 | 52.0% |
| 2   | 123  | 500   | Basic | Context | 260-240 | 48.0% (Context) |
| 3   | 777  | 1000  | Context | Basic | 520-480 | 52.0% |

**Combined full-game results:** ContextAwareAI wins 1020/2000 games = **51.0%**

### Single-Hand Games (target score = 1)

| Run | Seed | Hands | AI 1 | AI 2 | Wins (AI1-AI2) | Win Rate AI1 |
|-----|------|-------|------|------|----------------|--------------|
| 4   | 999  | 2000  | Context | Basic | 916-1084 | 45.8% |
| 5   | 888  | 2000  | Basic | Context | 1076-924 | 46.2% (Context) |

**Combined single-hand results:** ContextAwareAI wins 1840/4000 hands = **46.0%**

### Key Observations

**ContextAwareAI wins fewer individual hands but wins more full games.** This is the defining characteristic:

1. **Hand win rate:** ~46% (Context loses more individual hands than Basic)
2. **Game win rate:** ~51-52% (Context wins slightly more full games)
3. **How?** ContextAwareAI wins *bigger* when it wins:
   - Avg points per knock win: **17.0-17.8** (Context) vs **15.0-15.2** (Basic)
   - More gins: Context gets ~60% more gins than Basic
   - Massively more undercuts: Context undercuts ~5x more often than Basic
   - Avg points per undercut: **~27** (Context) vs **~26** (Basic)

### Detailed Metrics (from Run 3: 1000 full games, seed 777)

| Metric | ContextAwareAI | BasicAI |
|--------|---------------|---------|
| Games won | 520 (52.0%) | 480 (48.0%) |
| Rounds won | 4601 (46.8%) | 5222 (53.1%) |
| Total points | 85,212 | 80,868 |
| Gins | 184 | 129 |
| Knocks | 4,109 | 5,714 |
| Avg knock deadwood | 6.0 | 6.8 |
| Pts per knock win | 17.2 | 15.2 |
| Undercuts made | 615 | 123 |
| Undercuts received | 123 | 615 |
| Pts per undercut | 27.3 | 26.4 |
| Discard draw rate | 23.6% | 25.6% |

### Analysis

**ContextAwareAI's edge comes from quality over quantity:**
- Knocks less often but with lower deadwood (6.0 vs 6.8)
- Earns more points per knock win (+2 pts avg)
- Gets significantly more gins (+43%)
- Undercuts opponents ~5x more frequently (615 vs 123 in 1000 games)
- The undercut asymmetry is the biggest factor — Context is much better at detecting when opponent is likely to knock and keeping low deadwood defensively

**ContextAwareAI's weakness:**
- Wins fewer individual hands (~46%) — being more selective about knocking means BasicAI knocks first more often
- The hand-level disadvantage is overcome by winning bigger when it does win

**Position effect:**
- Player 1 (non-dealer, goes first) has a consistent ~52% win rate regardless of AI type
- This is a first-mover advantage inherent to gin rummy, not an AI difference
- When controlling for position, Context vs Basic difference is marginal at the game level

### Current ContextAwareAI Config

Key parameters (from `config/context-ai.toml`):
- `knock_decision_threshold = 0.4`
- `gin_pursuit_threshold = 3` (base, wait for gin when deadwood ≤ 3)
- `use_phased_knock = true` (three-phase knock strategy)
- `knock_phase_early_threshold = 0.25` (early game = first ~25% of deck dealt)
- `early_knock_bonus = 0.5` (knock aggressively early)
- `expanded_gin_pursuit_threshold = 6` (pursue gin with up to 6 deadwood if outs exist)
- `opponent_pickup_pressure_count = 3` (reduce gin pursuit threshold after 3+ opponent pickups)
- `denial_bonus = 0` (disabled)
- `safe_rank_discard_bonus = 0` (disabled)
- `dangerous_rank_penalty = 0` (disabled)
- All dynamic threshold modifiers disabled (`max_deck_modifier = 0`, `max_outs_modifier = 0`)
