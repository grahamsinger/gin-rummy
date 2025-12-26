# ContextAwareAI Improvement Plan

## Current State

ContextAwareAI currently beats BasicAI ~53% of the time. The only meaningful difference is in **draw decisions** - it uses dynamic thresholds and outs analysis. Knock and discard decisions are inherited from BasicAI.

### Context Available (but underutilized)

| Context | Current Use | Potential |
|---------|-------------|-----------|
| Deck position | Adjusts draw threshold | Could inform knock timing |
| Dead cards | Filters outs as unavailable | Could inform discard safety |
| Opponent pickups | Disabled denial bonus | Could predict opponent melds |
| Score differential | Adjusts draw threshold | Could inform knock/gin strategy |
| My outs | Adjusts draw threshold | Could prioritize protecting outs |

## Improvement Areas

### 1. Context-Aware Knock Decisions

**Current:** Knocks whenever deadwood ≤ 10 (same as BasicAI)

**Proposed:** Override `should_knock()` to consider:

```
IF score_differential > 30 (winning comfortably):
    → Be greedy, go for gin (only knock at 0-2 deadwood)

IF score_differential < -30 (losing badly):
    → Be aggressive, knock early (knock at ≤ 10)

IF deck_remaining < 30%:
    → Knock sooner (time pressure)

IF opponent_estimated_deadwood is low:
    → Knock sooner (avoid being undercut)
```

**Implementation:**
- Add `[context_aware_ai]` config options for knock thresholds
- Override `should_knock()` in ContextAwareAI
- Use opponent model to estimate opponent's hand strength

### 2. Context-Aware Discard Decisions

**Current:** Discards card that leaves lowest deadwood (same as BasicAI)

**Proposed:** Add "safety" scoring to discard candidates:

```
FOR each discard candidate:
    base_score = resulting_deadwood (lower = better)

    # Penalize unsafe discards
    IF opponent likely wants this card:
        penalty += UNSAFE_DISCARD_PENALTY

    # Bonus for discarding dead ranks/suits
    IF rank is "dead" (3+ cards of rank already discarded):
        bonus += SAFE_DISCARD_BONUS

    final_score = base_score + penalty - bonus
```

**What makes a discard "unsafe"?**
- Opponent picked up adjacent cards (building a run)
- Opponent picked up same rank (building a set)
- Card fits obvious opponent meld patterns

### 3. Improved Opponent Modeling

**Current:** Tracks rank/suit frequencies of pickups/discards

**Proposed:** Track likely opponent melds:

```python
class OpponentMeldTracker:
    """Track what melds opponent is likely building."""

    likely_runs: list[PartialRun]   # e.g., [7♥-8♥, likely wants 6♥ or 9♥]
    likely_sets: list[PartialSet]   # e.g., [K♠-K♥, likely wants K♦ or K♣]

    def record_pickup(self, card):
        # If adjacent to previous pickup in same suit → likely run
        # If same rank as previous pickup → likely set

    def cards_opponent_wants(self) -> set[Card]:
        # Return cards that would complete opponent's likely melds

    def estimate_opponent_deadwood(self) -> int:
        # Based on pickups and game length, estimate hand strength
```

### 4. Protecting Key Outs

**Current:** Doesn't consider whether discards block own outs

**Proposed:** Avoid discarding cards that are part of potential melds:

```
IF card is adjacent to cards in my hand:
    → Discarding it might block a future run

IF I have a pair and this is the 3rd card of that rank:
    → Keep it, could complete the set
```

## Implementation Priority

1. **Context-aware knocking** (highest impact, moderate effort)
   - Directly addresses the shared-config limitation
   - Score pressure and deck timing are clear signals

2. **Improved opponent modeling** (high impact, higher effort)
   - Foundation for safe discards and denial play
   - Need to track meld patterns, not just frequencies

3. **Safe discard selection** (medium impact, depends on #2)
   - Only valuable once opponent model is accurate

4. **Protecting own outs** (lower impact)
   - Edge case optimization

## Testing Approach

For each change:
1. Run 1000-game simulation (5 seeds × 200 games)
2. Compare win rate to baseline (currently 53.3%)
3. Track secondary metrics (gins, undercuts, avg deadwood)
4. If improvement ≥ 2%, keep the change

## Config Parameters to Add

```toml
[context_aware_ai]
# Knock decision parameters
knock_when_winning_threshold = 2      # Only knock at this deadwood when ahead
knock_when_losing_threshold = 10      # Knock at this deadwood when behind
score_lead_for_greedy = 30            # Points ahead to trigger greedy play
score_behind_for_aggressive = 30      # Points behind to trigger aggressive play
late_game_knock_bonus = 3             # Add to knock threshold late game

# Discard safety parameters
unsafe_discard_penalty = 2            # Penalty for discarding opponent's likely wants
safe_discard_bonus = 1                # Bonus for discarding "dead" cards
```
