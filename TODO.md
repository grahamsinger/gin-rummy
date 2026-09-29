# Gin Rummy - Open Work

Only open items live here. Finished work is in the git history (`git log -p -- TODO.md`
has the old checklists), simulation results are in `SIMULATION_HISTORY.md`, and the
2026-09 audit with its review log is in `AUDIT.md`.

## Known issues

- [ ] **A10 (Low): `_should_pursue_gin` EV comparison is vacuous** — `ai/context_aware.py`: `p*25 + (1-p)*ev_knock > ev_knock` holds for any p>0, so only the probability gate matters; gin value should be `25 + opponent_deadwood` and the probability denominator should account for opponent-held unknowns and remaining turns.
- [ ] **Perf (Low): MC draw fallback runs a full nested MC discard evaluation** — `ai/mc/ai.py`: the `_card_helps_hand` path invokes MonteCarloAI's own `decide_discard` on the hypothetical 11-card hand, doubling per-turn compute when the fallback triggers.
- [ ] **(Low) Defender meld arrangement vs layoff** — `calculate_layoff` fixes the defender's own melds to the minimal-deadwood arrangement first; a different equal-deadwood arrangement could occasionally enable a bigger layoff. Cards laid off within a fixed arrangement are optimal, but the arrangement choice itself isn't layoff-aware.
- [ ] **Test gaps** — no tests for `simulator/` (a 3-game smoke test would do), `analyze_hand.py` or `learning/experiment.py`; `cli/` and `db/` only have narrow regression tests. The learning tests need torch and skip locally (CI installs all extras, so they run there).

## Rule gaps (variants, decide if in scope)

- [ ] **Big gin** — an 11-card all-melded hand cannot be declared; the player must discard, and there is no big-gin bonus in config.
- [ ] **First-upcard take-or-pass** — standard gin offers the upcard to the non-dealer, then the dealer, before stock draws begin. This codebase uses the 11th-card variant (README), and Oklahoma mode deals an upcard but skips the take-or-pass phase.

## AI tuning

- [ ] **MC latency for web play** — sub-batch splitting (draw caps at 2 parallel tasks), a top-5 discard candidate cap, adaptive early stopping; consider a 500-sim "web hard" profile (~4.4s/turn vs ~19s at 2000 sims, see `experiments/mc_timing.py`).
- [ ] **Tune ContextAwareAI** (~52% game win rate, ~46% hand win rate vs BasicAI): wins fewer hands but bigger ones (more gins, more undercuts, higher points per knock).
- [ ] **Knock timing** — ContextAwareAI knocks almost as soon as deadwood drops below the threshold. Being able to knock doesn't mean one should: weigh the undercut risk from the opponent's discard pattern, the deck depletion, the score situation (behind → knock early, ahead → be selective) and gin pursuit at 1-3 deadwood against a safe knock now. Find which config parameters control eagerness and measure whether waiting improves the win rate.
- [ ] **Deadwood-based discard safety** — high cards (K, Q, J) are safer early (less meld potential), low cards riskier.
- [ ] **Discard-pile sequence memory** — weight recent discards higher than old ones; a card the opponent threw early but whose neighbours they picked up later may be wanted now.
- [ ] **End-game desperation mode** — when the deck is under 5 cards, lower every threshold, take any card that reduces deadwood, knock when able.
- [ ] **Denial bonus** — currently hurts performance (predictions inaccurate). Apply it only at high confidence (2+ pickups of the same rank) or remove it.
- [ ] **StatisticalAI** underperforms both heuristic AIs (`SIMULATION_HISTORY.md`, 2025-12-30). Train it against stronger opponents, reset and relearn, or tune the selection temperature.

## Card helpfulness ranking

The web assist panel ranks non-dead cards by the deadwood reduction a full draw-and-discard cycle would give. Still to do:

- [ ] Integrate into the outs analysis (outs are meld-completing only; this is any improvement).
- [ ] Add to the `analyze_hand.py` output: ranked helpful cards, "X helpful cards remaining (Y known dead)".
- [ ] Use it in AI draw decisions: few helpful cards left means a lower threshold late in the hand.

## UI

- [ ] **Dealer indicator** — show who dealt the current hand (a badge next to the name); the dealer alternates each round and the non-dealer goes first in Oklahoma Gin.
- [ ] **Manual card arrangement (drag & drop)** — reorder cards in hand with the HTML5 drag-and-drop API alongside the sort buttons, with a Reset to the last sort mode. Notes in `docs/archive/web-ui-spec.md`.

## Modes

- [ ] **"Grade my games"** — replay recorded human turns from the database through the scenario quiz's AI panel.
- [ ] **Tournament mode** with multiple rounds and scoring.
- [ ] **Undo last move** (within the same turn).
