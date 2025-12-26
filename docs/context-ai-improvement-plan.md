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

---

## Implementation Plan: Safe-Rank Discard Logic

### Overview

Add discard safety scoring to ContextAwareAI based on a simple heuristic:
**If opponent discarded a rank, they're not collecting that rank for a set, so it's safer to discard.**

### Heuristic

```
Opponent discards 7♥
  → Opponent is NOT building a set of 7s
  → Discarding 7♠, 7♦, 7♣ is "safe" (from a set perspective)
```

This is a naive but reasonable first step. It doesn't account for runs (opponent might still want 7♠ for a 5-6-7♠ run), but it's better than no safety consideration.

### Files to Modify

1. **`gin_rummy/context.py`** - Add helper method to OpponentModel
2. **`gin_rummy/ai.py`** - Override `decide_discard()` in ContextAwareAI
3. **`config/context-ai.toml`** - Add config parameter for bonus weight

### Step 1: Add `is_rank_safe()` to OpponentModel

**File:** `gin_rummy/context.py`

**Location:** Add after `predict_will_take()` method (around line 448)

```python
def is_rank_safe(self, rank: Rank) -> bool:
    """Check if a rank is safe to discard (opponent discarded this rank).

    If opponent discarded a card of this rank, they're likely not
    building a set of that rank, making it safer to discard.

    Args:
        rank: The rank to check.

    Returns:
        True if opponent has discarded this rank at least once.
    """
    return self.discarded_ranks[rank] > 0
```

### Step 2: Add Config Parameter

**File:** `config/context-ai.toml`

**Location:** Add under `# --- Bonus Adjustments ---` section

```toml
# Bonus for discarding a "safe" rank (opponent discarded same rank).
# When choosing between discards with similar deadwood impact,
# prefer ranks the opponent has shown they don't want.
safe_rank_discard_bonus = 1
```

**File:** `gin_rummy/config.py`

**Location:** Add to `ContextAwareAIConfig` dataclass

```python
safe_rank_discard_bonus: int = 1  # Bonus for discarding safe ranks
```

### Step 3: Override `decide_discard()` in ContextAwareAI

**File:** `gin_rummy/ai.py`

**Location:** Add new method to ContextAwareAI class (after `decide_draw()`)

```python
def decide_discard(self, hand: Hand) -> Card:
    """Context-aware discard decision with safety scoring.

    Extends BasicAI's deadwood-minimizing logic with a bonus for
    discarding "safe" ranks that opponent has shown they don't want.

    Args:
        hand: Current hand (should have 11 cards after drawing).

    Returns:
        Card to discard.
    """
    cards = list(hand)
    best_discard = None
    best_score = float('inf')  # Lower is better

    for i, card in enumerate(cards):
        remaining = cards[:i] + cards[i+1:]
        analysis = analyze_hand(remaining)

        # Base score is resulting deadwood (lower = better)
        score = float(analysis.deadwood_value)

        # Apply safety bonus (reduce score for safe discards)
        if self.opponent_model.is_rank_safe(card.rank):
            score -= self.context_config.safe_rank_discard_bonus
            logger.debug(
                "Safe rank bonus: %s (opponent discarded this rank)",
                card,
            )

        if score < best_score:
            best_score = score
            best_discard = card

    # Fallback (shouldn't happen)
    if best_discard is None:
        best_discard = max(cards, key=lambda c: c.deadwood_value)

    logger.info(
        "Discard decision: %s (score=%.1f, deadwood after=%d)",
        best_discard,
        best_score,
        int(best_score + self.context_config.safe_rank_discard_bonus
            if self.opponent_model.is_rank_safe(best_discard.rank)
            else best_score),
    )

    return best_discard
```

### Step 4: Ensure OpponentModel is Updated

**Verify:** The simulator and game runner already call `record_opponent_discard()` when opponent discards. Check these locations:

- `gin_rummy/simulator.py` - `_run_round()` calls `other_ai.record_opponent_discard(discard)`
- `gin_rummy/game_runner.py` - Should track discards in CLI mode too

### Testing Plan

1. **Unit test:** Verify `is_rank_safe()` returns correct values
   ```python
   def test_is_rank_safe():
       model = OpponentModel()
       assert not model.is_rank_safe(Rank.SEVEN)
       model.record_discard(Card(Rank.SEVEN, Suit.HEARTS))
       assert model.is_rank_safe(Rank.SEVEN)
   ```

2. **Simulation test:** Run 1000 games with different bonus values
   ```
   safe_rank_discard_bonus = 0  → baseline (should match current 53.3%)
   safe_rank_discard_bonus = 1  → small preference for safe discards
   safe_rank_discard_bonus = 2  → stronger preference
   safe_rank_discard_bonus = 3  → very strong preference
   ```

3. **Analyze results:**
   - Does win rate improve?
   - Track undercuts received (should decrease if discards are safer)
   - Track opponent gins (should decrease if we're not feeding them cards)

### Expected Behavior

| Scenario | Before | After |
|----------|--------|-------|
| Opponent discards 7♥, we have 7♠ as potential discard | No preference | Slight preference to discard 7♠ |
| Two discards with same deadwood impact (e.g., 5♣ and 7♠) | Random/arbitrary | Prefer 7♠ if opponent discarded a 7 |
| Discard with lower deadwood vs safe discard | Always pick lower deadwood | Still pick lower deadwood (bonus is small) |

### Future Enhancements

Once this basic version is working:

1. **Suit safety for runs:** Track which suits opponent is discarding to infer run-building
2. **Pickup-based danger:** Penalize discards matching opponent's pickup patterns
3. **Combined scoring:** Weight both rank safety (sets) and suit safety (runs)
