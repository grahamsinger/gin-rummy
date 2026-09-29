# Codebase Audit

> ## Latest review: ruff expansion + worker pool (`defb186`…`94b8076`), 2026-09-28
>
> **Verdict: verified. Behaviour preserved everywhere it should be, and the pool fix works.** Nothing blocking; a few nits.
>
> **Checks at `94b8076`:** 345 tests pass, `ruff check` (now `F,E,W,I,UP,B,SIM`) and `ruff format --check` are clean, eslint shows 0 warnings, and the fingerprint is unchanged (`49ebb018605bbae6` / `56c04fee7ecf6e24`). **`ty` went up from 43 to 52**, and all 9 new diagnostics are in `tests/test_worker_pool.py` (see nits).
>
> | Commit | What | Verified |
> |---|---|---|
> | `defb186` | Golden rows now include `cards_before`/`cards_after` and the AI decisions | ✅ The hand lists in both golden files equal my independent pre-step-3 dump from `a2f4989` |
> | `0416d96` | `I` + `UP` auto-fixes | ✅ **Purely mechanical:** re-running `ruff check --fix` + `ruff format` on its parent with its `pyproject.toml` reproduces it exactly (0 diff lines). Blame-ignored in `0a1fd6a` |
> | `f6649b6` | `B` + `SIM` fixed by hand (19) | ✅ Every change read. All are equivalent rewrites: ternaries, `contextlib.suppress` for the column migrations, a merged `if`, the CLI assist toggle (same logic), `.values()` loops, and `strict=True` on 3 quiz `zip`s over lists derived from the same panel plus 2 in tests. `game_id = g + 1` in `stress_test_db.py` equals the old top-of-loop increment (no `continue`) |
> | `eeb406d` | Shared worker pool, `close()`, sync routes + per-session lock, AI kept across hands | ✅ See below |
>
> **Worker pool (`eeb406d`) in detail:**
> - **Ownership is correct.** `MonteCarloAI(pool=)` borrows the pool and `shutdown()` only stops pools the AI owns, so neither `__del__` nor `close()` can kill the shared pool. `web/workers.py` creates it lazily under a lock and the lifespan shuts it down after `session_store.close_all()`. `ProcessPoolExecutor.submit` is thread-safe, so sessions sharing it from threadpool routes is fine.
> - **Keeping the AI across hands is safe.** MonteCarloAI doesn't override `reset_for_new_hand`, so `_turn_plan` and `last_mc_thinking` now survive into the next hand. I traced both:
>   - `_turn_plan` is cleared by every `decide_draw` (`monte_carlo.py:776`) and overwritten by `decide_discard`, and one of those always runs before `should_knock` can read it.
>   - The session clears `last_mc_thinking` after every AI turn (`game_session.py:760`).
>
>   So nothing stale is used or shown.
> - **Locking:** every game and scenario route that mutates the session holds `session.lock`, and the scenario session borrows the same lock.
>
> **Nits (optional):**
> 1. **`tests/test_worker_pool.py` adds 9 `ty` diagnostics:**
>    - A generator fixture is annotated `-> Config`; it should be `-> Iterator[Config]`.
>    - `session.game` and `session.ai` are used without narrowing `Optional`. Add an `assert ... is not None`.
>    - `pool.submit(abs, -1)` is a `ty` false positive; any picklable function would avoid it.
> 2. **`MonteCarloAI` should clear `_turn_plan` and `last_mc_thinking` in its own `reset_for_new_hand()`.** It's safe today only because of the call ordering traced above, and it's cheap insurance now that AIs live across hands.
> 3. **`_get_scenario_session` (`app.py`) creates the `ScenarioSession` before taking the lock.** Two simultaneous first requests could each build one, and the second would win. That's harmless (it's a borrowed pool, so nothing leaks), but it could move inside `session.lock`.
> 4. **Edge case:** if `monte_carlo_ai.max_workers = 1`, `get_worker_pool()` returns `None`, and the scenario panel's MC AI (built with `WEB_MC_WORKERS = 8`) then starts its **own** 8-process pool. Pass the configured worker count to the panel, or treat "no shared pool" as "run inline".
> 5. **Behaviour to be aware of (by design):** concurrent "hard" games now share one 15-worker pool, so under load each MC turn gets slower instead of the machine being oversubscribed.
> 6. **Doc accuracy:** "Next up" 0 below says the mechanical `I`+`UP` commit is `0a1fd6a`. It's actually `0416d96`; `0a1fd6a` is the commit that adds it to `.git-blame-ignore-revs`.
>
> ## How reviews are verified (for any agent picking this up)
>
> - **Behaviour fingerprint at any commit:** `git worktree add <scratch>/<sha> <sha>`, then run `<repo>/.venv/bin/python <scratch>/<sha>/scripts/fingerprint.py` (the script re-execs with `PYTHONHASHSEED=0` and puts its own checkout first on `sys.path`). Check the import really comes from the checkout, e.g. `hasattr(Card, "code")` is false before `f6aeb6b`. Remove the worktrees afterwards.
> - **Mechanical commits** (format, `ruff --fix`): check out the parent, apply the commit's `pyproject.toml`, re-run the tool, and `git diff <commit>` should be empty.
> - **Recording changes:** `tests/golden/` holds the seeded CLI and web rows; `UPDATE_GOLDEN=1` accepts an intentional change.
> - **Reviews are read-only:** never commit, merge or edit code while verifying. Findings go at the top of this file.

> ## Earlier review: consolidation follow-ups (`8424e62`, `6bef1bc`), 2026-09-28
>
> **Verdict: all five follow-ups resolved correctly.** Nothing blocking; two optional nits.
>
> **Checks at `6bef1bc`:** 342 tests pass, `ruff check` and `ruff format --check` are clean, eslint shows 0 warnings, `ty` reports 43, and the behaviour fingerprint is unchanged (`49ebb018605bbae6` / `56c04fee7ecf6e24`).
>
> | # | Follow-up | Resolution | Verified |
> |---|---|---|---|
> | 1 | B9 leftover in `learning/state.py` | Falls back to `get_config().game_rules.knock_threshold` instead of `10` | ✅ Matches `BasicAI._knock_threshold_for`; the docstring was updated too |
> | 2 | Mixed card formats in `ai_decisions` | `TurnRecorder` stores `discard.card.code`; `replay.js` formats anything matching `^(10\|[2-9AJQK])[SHDC]$` with `CardUtils.formatCardId` and passes other values through | ✅ Old display-string rows (`K♦`) still render. Old *CLI* rows, which already stored codes like `KD`, now render as proper cards too. Draw/knock choices (`DECK`, `knock`) don't match the pattern, so they pass through unchanged |
> | 3 | StatisticalAI cores have side effects | Comment on the class explaining that one of plain/twin must be called per decision | ✅ The comment-only option is fine, since the runner calls exactly one |
> | 4 | Silent fallback for unknown difficulty | `ai_difficulty` and both draw `source` fields are now `Literal`, so bad input gets a 422 from FastAPI | ✅ Only `easy`/`medium`/`hard` have ever existed in `index.html`'s history, so a value saved in localStorage can't trip the new validation. The resume path (`game_session.py:288`) still uses `DIFFICULTY_TO_AI.get(..., "context")`, which is fine because stored values came through the same input |
> | 5 | Golden turns rows | `tests/golden/turn_rows_{cli,web}_seed7.json` plus `_check_golden()`, with `UPDATE_GOLDEN=1` to accept intentional changes | ✅ **Independently confirmed:** both golden files equal the rows I dumped from `a2f4989` (before the step-3 refactor), 13 rows each. So the golden data captures the original behaviour, not the refactored code's output |
>
> **Nits (optional):**
>
> - **The golden rows cover 7 of the `turns` columns** but not `cards_before`/`cards_after`, and not `ai_decisions`. The invariant check still validates the card sets, but a change in stored hand *order*, or in which decisions get recorded, would slip through. Adding `cards_before`, `cards_after` and `(decision_type, choice)` per turn would make the golden test complete.
> - **In `web/app.py`, `from typing import Literal` sits between the FastAPI and pydantic imports.** Enabling ruff's `I` rule (§6) would sort it automatically.

> ## Next up (decided 2026-09-28)
>
> ### 0. ~~Expand the ruff rules (`I`, `UP`, `B`, `SIM`): do first, it's small~~ Done (`0416d96` mechanical `I`+`UP`, blame-ignored in `0a1fd6a`; `f6649b6` `B`+`SIM` by hand, `zip(strict=True)` where lengths are derived from the same list)
>
> `pyproject.toml` only selects `F`, `E`, `W`. Counted at `6bef1bc` with `ruff check --select I,UP,B,SIM --statistics`: **65 hits**.
>
> | Rule | Hits | Auto-fix |
> |---|---|---|
> | `I001` unsorted imports | 42 | yes |
> | `UP035` / `UP037` outdated syntax | 3 + 1 | yes |
> | `SIM118` | 1 | yes |
> | `SIM108` / `SIM105` / `SIM102` / `SIM113` | 6 / 2 / 1 / 1 | by hand |
> | `B905` `zip()` without `strict=` | 5 | by hand |
> | `B007` unused loop variable | 3 | by hand |
>
> 1. **Commit 1, mechanical:** add `I` and `UP` to `select`, then run `ruff check --fix`. Add the commit to `.git-blame-ignore-revs`, and keep `AUDIT.md` out of it.
> 2. **Commit 2, by hand:** add `B` and `SIM`, then fix the 19 remaining hits. Read each `B905` (`zip` without `strict=`) carefully: if the lists can differ in length, `zip` silently drops items, which is a potential real bug. Use `strict=True` where equal length is expected.
> 3. **Verify:** tests, plus `scripts/fingerprint.py` unchanged. Re-sorting imports can change behaviour when a module has import-time side effects or circular imports.
> 4. **Why now:** it's before the file splits (order of work, step 8), so moved code doesn't carry import churn. After this, pre-commit and CI keep imports sorted.
>
> ### A. ~~Monte Carlo worker-pool lifecycle (web): fix before the round runner~~ Done (commit after `f6649b6`): shared pool in `web/workers.py`, `MonteCarloAI(pool=)` borrows it, `GameSession.close()` on eviction and lifespan exit, AI kept across hands, routes sync + per-session lock, regression test in `tests/test_worker_pool.py`
>
> **Correction to §4:** the pools do **not** currently leak. Measured on 2026-09-28 by counting child processes of a real `GameSession` on "hard" (15 workers + 1 resource tracker = 16):
>
> | Action | Child processes |
> |---|---|
> | First MC AI spun up | 16 |
> | `self.ai` replaced with a new MC AI, 3× (no `gc.collect()`) | 16 each time |
> | Session dropped | 1 |
> | Session expired via `SessionStore.cleanup_expired()` | 1 |
>
> CPython runs `MonteCarloAI.__del__` (`monte_carlo.py:682`) as soon as the last reference goes away, and that shuts the pool down. The real problems:
>
> 1. **Cleanup works only by accident.** It depends on nothing else holding a reference to the AI or the session. One future reference cycle (a callback or closure that captures the session, an AI that holds its game) and every replaced "hard" AI leaks `cpu_count - 1` processes until the garbage collector happens to run. `__del__` is also not guaranteed at interpreter exit, and nothing shuts pools down on app shutdown (`app.py:74-85` lifespan).
> 2. **A new pool every hand.** `new_round` builds a new AI (`game_session.py:872`, also `:256`, `:306`), and every `MonteCarloAI` lazily starts its **own** `ProcessPoolExecutor` (`monte_carlo.py:571-580`). That's 15 processes on a 16-core machine, started from scratch each hand, and with macOS's `spawn` start method each worker re-imports the package.
> 3. **No cap across sessions.** Each concurrent "hard" game, and each scenario-quiz panel (`app.py:545`), holds its own pool, so N sessions means about 15N processes.
> 4. `ScenarioSession.shutdown()` (`scenario_session.py:54`) is never called, and session eviction (`session_store.py:47, 59`) just drops the entry. This works today only because of point 1.
>
> **Fix:**
> - **One shared, app-level worker pool.** Create it in the lifespan, shut it down on exit, and pass it to MC AIs, which should no longer own pools. This removes the per-hand startup cost and caps total processes.
> - **An explicit `GameSession.close()`** that `SessionStore` calls on eviction, so cleanup doesn't rely on `__del__`.
> - **Keep the AI across hands.** Call `reset_for_new_hand()` in `new_round` instead of building a new AI.
> - **A regression test** that replaces the AI and expires a session, then asserts the child-process count is stable (the measurement above is the template).
>
> **Related, same area (§4):** the MC turn and scenario routes are `async def` but do seconds of CPU work, so they block every user for 2–4 s. Run them in a threadpool with a per-session lock. With a shared pool, that thread mostly waits on worker futures.
>
> ### B. ~~Round runner (§2.1): design decided~~ Done (2026-09-28)
>
> Commits, in order: `7b4f715` safety net; `3e3542a` opponent-tracking alignment (behaviour, see below); `c386d82` the runner; `8776d09` `other_ai` dropped from `execute_ai_turn`.
>
> - **`gin_rummy/round_runner.py`:** `run_round(game, seats, stop_when=)` plays a dealt round: the non-dealer seat's opening discard, turns until a knock or the deck runs out, every opponent action relayed to the other seat. `Seat` decides (a prompt or an AI); `AISeat` is the plain AI seat with optional turn callbacks. Callers: simulator (`_TimedSeat`), scenario quiz (`stop_when` freezes the hand at the human seat), trainer (`_LearnerSeat` collects experiences), CLI (`CLIHumanSeat`, `CLIAISeat`). The web session stays request-driven.
> - **`3e3542a` is the one behaviour change**, made before the runner so the runner could be uniform without per-caller flags: the scenario seat AIs learn the opening discard; the trainer's learner starts every game with a fresh opponent model and evaluation rounds track the opening discard; the CLI and web AIs now observe the human's opening discard, pickups and discards, and the CLI AI is reset each round. Only the learning fingerprint moved (`7427fe2bda5dd730` → `d14855bd28ce8d14`); CLI/web/scenario goldens are unchanged.
> - **Safety net now in `scripts/fingerprint.py`:** four lines. `primary 49ebb018605bbae6`, `secondary 56c04fee7ecf6e24`, `scenario 458764989f15a853` (20 seeded positions + panel draw advice), `learning d14855bd28ce8d14` (4-episode seeded run, float-sensitive, `--no-learning` to skip). `tests/golden/scenarios_seed7.json` pins five positions; `TrainingConfig.seed` / `gin-train --seed` seed random, numpy and torch.
> - **Next:** §3 file splits (the large modules), then the frontend, then docs/TODO cleanup.
>
> Original design notes:
>
> - **Approach (b):** a blocking round runner for the four loop-style callers (CLI vs AI, CLI PvP, simulator, scenario quiz), plus the trainer's round loop. The **web session stays request-driven**; it already shares the turn-level pieces (`execute_ai_turn`, `TurnRecorder`, `end_hand_from_result`). Seats provide the decisions (human prompt, AI).
> - **Safety net before starting:**
>   - **Simulator:** covered by `scripts/fingerprint.py`.
>   - **CLI:** covered by the golden `turns` rows in `tests/golden/`.
>   - **Scenario quiz:** needs a seeded fingerprint of the generated scenarios.
>   - **Trainer:** needs a `--seed` (including torch seeding, §4 Randomness) and a short seeded training-run fingerprint.

> ## Previous review: core consolidation (`6a033ee`…`9e76db6`), 2026-09-28
>
> **Verdict: verified. The four steps preserve behaviour where they claim to.** No blocking issues; five small follow-ups below.
>
> **What was independently checked** (read-only; temporary checkouts in a scratch directory, all removed):
>
> - **Checks at `9e76db6`:** 342 tests pass, `ruff check` and `ruff format --check` are clean, eslint shows 0 warnings, and `ty` reports 43 diagnostics.
> - **Behaviour fingerprint at every step.** `scripts/fingerprint.py` (150 games, seed 42) was run against `6a033ee` (baseline), `f6aeb6b`, `37ec056`, `06d3307`, `1eb5d6d` and `3297c87`.
>   - All six give `49ebb018605bbae6` / `56c04fee7ecf6e24`, wins 62-88 and 134-16.
>   - Each run was confirmed to import its own checkout's code: the baseline has no `Card.code`.
>   - Runtime stayed at about 24 s per run, so ContextAwareAI's plain path now building reasoning strings costs nothing measurable.
> - **Recorded rows, before vs after step 3.** The same seeded CLI and web rounds were played on `a2f4989` (just before step 3), `1eb5d6d` and `9e76db6`, and the stored rows diffed (ids and timestamps excluded):
>   - `turns` and `hands` rows: **identical** for both UIs.
>   - Web `ai_decisions` rows: **identical**.
>   - CLI `ai_decisions` rows: **changed, as the commit message says** (intentional). The CLI now stores the same structured reasoning as the web UI. That means uppercase `DISCARD`/`DECK`, a knock row every turn, and full `options_considered`, where it used to store generic strings like `"Drew 3S from discard"`. Existing databases therefore hold both formats for CLI games. The replay view only displays `choice` as text, so nothing breaks.
>   - `tests/test_turn_recording.py` was added in the same commit as the refactor, so it never ran against the old code. It **does pass on `a2f4989`**, so its invariants held before and after.
> - **Code read:**
>   - `Card.code`/`parse`/`index`/`from_index`/`__hash__`. The hash is consistent with equality, and `T` is accepted on input only.
>   - `ai/factory.py`, `tracking.py`, the `BasicAI` interface and `_evaluate_*` cores, the ContextAwareAI plain→reasoning binding (pinned so MonteCarloAI's `super()` fallbacks can't recurse), the StatisticalAI/LearningAI twins, the B9 threshold plumbing, and `test_reasoning_agreement.py`.
>
> **Follow-ups (all minor):** _all five addressed in `8424e62` and the commit after it: configured threshold fallback in the state encoder; discard `choice` stored as `Card.code` with the replay view formatting codes (old display-string rows still render); side-effect comment on the StatisticalAI cores; `ai_difficulty` and draw `source` validated as `Literal` in the request models; golden `turns` rows for the seeded CLI and web rounds in `tests/golden/` (regenerate with `UPDATE_GOLDEN=1`)._
>
>
> 1. **One B9 leftover:** `learning/state.py:142` still falls back to a hard-coded `10` when no context is given. Use the configured `game_rules.knock_threshold`, as `BasicAI._knock_threshold_for` does.
> 2. **Mixed card formats in `ai_decisions`:** the discard `choice` is stored as the display string (`str(card)`, e.g. `K♦`), while every other card column in the DB uses `Card.code` (`KD`). This was already true in the web UI and now applies to the CLI too. Consider storing `Card.code` and formatting for display in JS, or document it as display-only.
> 3. **StatisticalAI's `_evaluate_stats_*` cores have side effects:** they append to `_round_knocks`, and discard stats are recorded unless `_in_hypothetical`. That's fine while the runner calls exactly one of plain/twin per decision. Anything that calls both on the same instance would record twice, which is why the agreement test correctly uses fresh instances. Worth a comment on the cores, or move the recording out of them.
> 4. **`DIFFICULTY_TO_AI.get(difficulty, "context")` silently maps unknown difficulties to medium** (`game_session.py:256, 306, 872`). Validate `ai_difficulty` as a `Literal` in the request model (see §4, Web server).
> 5. **Optional:** turn the before/after row diff above into a real golden test. Commit the expected `turns` rows for the seeded CLI and web rounds, so the next recording change is compared against actual data, not just invariants.

_Audited at commit `779a7ad` (2026-09-28). Line numbers refer to that commit and will drift._

**Summary:** about 25k lines of source. There are 263 passing tests (1 skipped), 76 ruff errors, 42/57 files not ruff-formatted and 79 `ty` diagnostics. There is no CI. _As of the core consolidation (step 4, 2026-09-28): 342 tests pass, ruff reports 0 errors, every file is ruff-formatted, CI runs on push, and `ty` reports 43 diagnostics (was 79)._

The biggest structural problem is that the **game/round loop is implemented four separate times**: CLI vs AI, CLI PvP, simulator and scenario quiz (a fifth copy, the network server, was deleted on 2026-09-28). The web session and trainer run partial copies. Result recording and card serialization are copied in the same way. Several real bugs below come directly from those copies drifting apart.

---

## 0. Bugs found during the audit (fix first)

Items marked ✅ were spot-checked by hand. The rest come from reviewer reads. The **Status** column shows what has been done since the audit.

**Progress (2026-09-28):** B1–B6 were re-confirmed against the code and fixed in commits `1646e4e`–`e196cf6`, each with a regression test. Second batch (`2c8224b`–`72c06c3`) fixed B7, B12, B13, B14, B15 and the two B5 follow-ups below, and added the §5/§6 safety net. B8 and B9 were fixed with the reasoning-twin merge (§2.4). The **B7 regression** found in the second review below was fixed in `23d25b6`; the other follow-ups from that review (reason assertion, `learning` marker, CPU-only torch index for CI, duplicate test id) landed right after.

**Review of the fix commits (`1646e4e`, `cb442ff`, `b506c21`, `e196cf6`):** all four were read in full and verified. **291 tests pass** (was 263). Ruff errors went from 76 to 70, and the touched files add no new lint. Notes and follow-ups:

- **B1/B10, network removal:** clean. No references to `network`, `gin-server` or `gin-client` remain in code, config, README or docs.
- **B2/B3/B11, CLI recording and the SQL fix:** correct. The removed CLI blocks used to derive a PvP `+25`. `end_hand_from_result()` now takes `points`, `is_gin` and `is_undercut` straight from `RoundResult`, so config bonuses and layoffs are respected, and all three recording sites share one mapping.
- **B4, opponent tracking:** correct. The trainer's rounds go through `execute_ai_turn` (`trainer.py:455, 664`), so the fix reaches training as well as the simulator and CLI. The `getattr` duck-typing is an interim step; it should become the `AIPlayer` protocol in §2.3, as the code comment says.
- **B5, checkpoint resume:** correct. The checkpoint loads into the existing networks, so the optimizers keep training the right parameters. Two small follow-ups remain:
  - **Off by one:** `_save_checkpoint(episode)` runs *after* episode `e` completes and stores `episode=e`. Resume starts `range(self._start_episode, ...)` at `e`, so that episode is trained twice. Store `episode + 1`, or resume from `+1`.
  - **`--episodes` is a total, not additional episodes.** Resuming from a final checkpoint (`episode == num_episodes`) with the same `--episodes` trains nothing and just re-saves. Either log a warning when `_start_episode >= num_episodes` or document that `--episodes` is the total.
  - The replay buffer isn't checkpointed, so a resumed run starts with an empty buffer. That's acceptable, but worth a line in `docs/learning-ai.md`.
  - _All three addressed in `2c8224b`: checkpoints store completed episodes, `train()` warns when there is nothing left to train, and the docs note both._
- **B6, XSS:** correct and complete for player names. Names in `data-players`/`data-player1` attributes are escaped. When the page reads them back, they go into `textContent` (`history.js:493`) or into `HandReplay`, which escapes them again, so there is no second injection point. The only remaining unescaped interpolation is `scenario.js:202` (`row.name`), and that's safe for now because those names are fixed, server-side AI panel names. `HandReplay.escapeHtml` (`replay.js:527`) now delegates to `CardUtils.escapeHtml`, so there is a single implementation.

**Review of the second batch (`2c8224b`, `f68eb01`, `2174d93`, `0b76869`, `72c06c3`, `3b8bfb5`):** all were read in full and the checks re-run at `8c65454`: **307 tests pass**, `ruff check` is clean, `ruff format --check` is clean (59 files), eslint shows 0 warnings, and `ty` reports **63** diagnostics (was 79). The format commit `0b76869` was verified as purely mechanical: re-running `ruff check --fix` + `ruff format` (0.14.14) on its parent reproduces it exactly, apart from `AUDIT.md`. That file was bundled into the same commit, so its edits are hidden from blame too; that's harmless, but keep docs out of blame-ignored commits in future. Notes:

- ~~⚠️~~ **B7 fix regressed gin / deck-nearly-empty knock reasoning** (fixed in `23d25b6`, with the suggested test). In `MonteCarloAI.should_knock`, both shortcut paths store `knock_thinking` with a `reason` and then immediately call `self._clear_thinking("knock")` (`monte_carlo.py:1110` and `:1136`). `should_knock_with_reasoning` (`:1376`) then falls through to the `(fallback)` branch, so the DB and the MC thinking panel show `Knocked: deadwood=0 (fallback)` instead of `Knock (gin): deadwood=0`. **Fix:** delete those two `_clear_thinking` calls; they belong only on paths that *don't* record thinking. **Test to add:** `should_knock` on a gin hand leaves `last_mc_thinking["knock"]["reason"] == "gin"`. `TestThinkingReset` covers only the clearing direction, which is why this passed.
- **B5 follow-ups:** correct. Periodic saves store `episode + 1` and the final save stores `num_episodes`, so both mean "completed episodes". The warning and the docs line are in. Checkpoints written before `2c8224b` still store the old `e` value, so resuming one of them retrains one episode, which is harmless.
- **B12:** correct. `reset_panel_tracking()` is shared by the CLI quiz and `web/scenario_session.py`, and it runs before every generation attempt.
- **B13, B15:** correct. `stress_test.db` is now in `.gitignore`.
- **B14:** correct. The new `id_to_card` parses `rank = id[:-1], suit = id[-1]` and raises `ValueError` on anything it doesn't know (including lowercase), and the route maps that to 400. `tests/test_web_app.py` covers it at both the unit and HTTP level. (`"10"` appears twice in the HTTP test's bad-id list; harmless.)
- **`init_db()` in the web lifespan:** a good catch beyond the audit; history and stats routes previously failed on a fresh DB.
- **Test infra:** `conftest.py` patches `database.get_db_path`, and all three callers (`init_db`, `get_connection`, `GameTracker.__init__`) resolve it at call time, so isolation holds, including for the app lifespan under `TestClient`. ~~The `learning` marker is registered but not yet applied to `test_learning.py`.~~ Applied.
- **`2174d93` (hand fixes for ruff):** behaviour-preserving. The removed `non_terminal_mask` in `replay.py` was computed and never used, and the `simulator.py` import move is safe because the lazy `LearningAI` helper doesn't depend on import order.
- **CI:** the workflow looks right, and the pre-commit ruff rev (`v0.14.14`) matches the locked ruff. One cost issue: the install step is labelled "CPU torch", but nothing selects a CPU index. `uv.lock` resolves the CUDA build (51 `nvidia-*` entries), so every CI run downloads several GB. Add a `pytorch-cpu` index in `[tool.uv.index]` / `[tool.uv.sources]` (with a Linux marker) to make CI much faster. _Done: the lock now has 0 `nvidia-*` entries; Linux resolves `torch 2.14.0+cpu`, macOS keeps the PyPI build._
- **Dead JS (`3b8bfb5`):** correct. `getState`/`knock` had no callers. The rest of the knock-confirm flow (modal, CSS, `/api/game/knock`, `GameSession.knock`) is still listed in §4.

| # | Bug | Location | Status |
|---|---|---|---|
| B1 ✅ | **`network/` cannot be imported.** It imports `gin_rummy.card`/`gin_rummy.melds`, which moved to `gin_rummy/models/`. The `gin-server`/`gin-client` entry points crash. See §1. | `network/server.py:15`, `client.py:13`, `protocol.py:15` | **Fixed** by deleting `network/` (see §1) |
| B2 ✅ | **CLI records wrong round results to the DB.** `p*_score_before` is read *after* scoring, so `points` is always 0. The winner comes from cumulative score, gin is "anyone has 0 deadwood", and the knocker is assumed to be `1 - current_player_idx`, but `knock()` doesn't switch players. PvP hard-codes `+25`. | `cli.py:759-790`, `cli.py:838-865` | **Fixed.** Both CLI loops and the web session now record via `GameTracker.end_hand_from_result()`. Tests: `test_cli.py`, `test_database.py` |
| B3 ✅ | **SQL correlation bug.** In `EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = id)`, the unqualified `id` resolves to `t.id`, so resume can choose the wrong dealer. Use `hands.id`. | `database.py:813` | **Fixed.** Test: `test_database.py::TestResumableGame` |
| B4 ✅ | **LearningAI never sees opponent actions.** `record_opponent_pickup/discard` only forward to `ContextAwareAI` instances, so ~34 opponent-model state features stay empty during training. | `game_runner.py:144,155` | **Fixed.** Forwarders now duck-type on the method. Tests: `test_game_runner.py`, `test_learning.py` |
| B5 ✅ | **`--resume` trains the wrong network.** It replaces `trainer.learning_ai`, but the optimizers still hold the old network's parameters. Curriculum and exploration state are not restored either. | `learning/trainer.py:737-742` vs `:152-163` | **Fixed.** `Trainer.load_checkpoint()` loads into the existing networks and restores exploration/curriculum/episode. Test: `test_learning.py::TestTrainerResume` |
| B6 ✅ | **Stored XSS via player names.** Names from the DB go into `innerHTML` unescaped. `escapeHtml` exists only as a private `HandReplay` method. | `game.js:404-409, 621, 1606, 1701-1716, 1753`; `history.js:~236-265` | **Fixed.** Shared `CardUtils.escapeHtml` used at every name interpolation in `game.js`, `history.js`, `replay.js` |
| B7 | MonteCarloAI early returns don't reset `last_mc_thinking`, so the `*_with_reasoning` wrappers report the previous turn's numbers. | `ai/monte_carlo.py:746, 846, 1049, 1120` | **Fixed** (`2c8224b`, regression fixed in `23d25b6`). `_clear_thinking()` runs only on early returns that skip simulation. Tests: `test_monte_carlo.py::TestThinkingReset` covers both clearing and keeping the gin / deck-nearly-empty reasons |
| B8 | StatisticalAI and LearningAI inherit `BasicAI.*_with_reasoning`, so the reasoning stored in the DB describes greedy-deadwood logic, not the real decision. | `ai/basic.py:234-395` | **Fixed** (§2.4). StatisticalAI and LearningAI have their own reasoning twins; `tests/test_reasoning_agreement.py` showed 94 disagreements for StatisticalAI before the fix |
| B9 | The Oklahoma knock threshold is ignored outside ContextAware/MC, which hard-code `10`. | `context_aware.py:360,415,800,847`, `basic.py:192`, `statistical.py:249`, `learning_ai.py:268`, `learning/state.py:161` | **Fixed** (§2.4). Every AI reads `context.knock_threshold` when a context is given; tests in `test_ai.py::TestKnockThresholdFromContext` and `test_learning.py` |
| B10 | Network server `_handle_knock` edits hand and discard pile directly, bypassing the discard-back rule and `_discard_history`. It also catches the wrong exception type. | `network/server.py:371-386` | **Gone** with `network/` |
| B11 | The CLI PvP first discard prompts "1-11" but shows the hand without numbers and indexes the unsorted hand. | `cli.py:810`, `cli.py:328` | **Fixed.** PvP reuses `play_human_first_discard` |
| B12 | The scenario quiz doesn't reset panel AI tracking between failed generation attempts. | `scenario_quiz.py:340-345` vs `409-411` | **Fixed** in both the CLI quiz and `web/scenario_session.py` via `reset_panel_tracking()` per attempt |
| B13 | Duplicate `@keyframes pulse`: the second definition silently overrides the AI-pickup animation. | `style.css:1021` and `:1552` | **Fixed.** Second one renamed `pulse-soft` |
| B14 | `id_to_card("10")` raises `IndexError`, which `GameSession.discard` doesn't catch, so it returns a 500. | `web/game_session.py:829` | **Fixed.** `id_to_card` raises `ValueError`; route returns 400. Test: `test_web_app.py::TestValidation` |
| B15 | `scripts/stress_test_db.py` inserts schema version `2`, but `SCHEMA_VERSION = 4`. The trainer progress string contains a stray `\ngts`. | `scripts/stress_test_db.py:45`, `trainer.py:782` | **Fixed** (both halves) |

---

## 1. ~~Decision needed~~ Done: the `network/` package was deleted (commit `1646e4e`)

_Original text kept for the rebuild notes._ `network/` hadn't kept up with the engine (B1, B10). It has its own game loop, its own card codec (`protocol.py:~90-141`) and its own state-for-player builder (`server.py:68-90`), all of which duplicate code elsewhere. Nothing tests it.

**Recommendation: delete it now, and rebuild multiplayer on the web stack later if it's still wanted.**

- The web app is the maintained interface. `GameSession` already has the state serialization, turn flow and DB recording that a multiplayer server needs.
- To rebuild: add a WebSocket route (FastAPI supports it natively) that lets two human seats share one `GameSession`, reusing the shared round runner proposed in §2.1.
- Deleting removes ~1,300 lines. It also removes `gin-server`/`gin-client` from `pyproject.toml:15-16` and the README "Network Multiplayer" section (README.md:168-178).

---

## 2. Code that should be combined

### 2.1 One round runner instead of four game loops
_Done (`c386d82`): `gin_rummy/round_runner.py` with `Seat`/`AISeat`/`run_round`; the CLI, simulator, scenario quiz and trainer loops are seats over it. See "Next up" B above._

Game loops are implemented in `cli.py:704-795`, `cli.py:798-870`, `simulator.py:353-416` and `scenario_quiz.py:113-150`. Partial copies live in `web/game_session.py` and `learning/trainer.py:355-517`.

**Target:** `gin_rummy/engine/round_runner.py` with a `Seat` interface (human prompt, AI, remote/web client) that returns a `RoundResult`. `game_runner.execute_ai_turn` is already shared by CLI and web; extend that pattern.

### 2.2 One result/turn recorder
_Done (`cb442ff`, `1eb5d6d`): `GameTracker.end_hand_from_result()` and `gin_rummy/tracking.py` (`TurnSnapshot`, `TurnRecord`, `TurnRecorder`) replace the copies; `tests/test_turn_recording.py` checks the rows written by the CLI and the web session._

- Turn recording is copied **five times**: `cli.py:504-516, 526-539, 585-630`; `game_session.py:787-830, 893-920`.
- The draw-hand `end_hand(...)` block is copied at `cli.py:750-758, 829-837` and `game_session.py:701-709`.
- ~~The web version uses `RoundResult` correctly and the CLI doesn't (B2).~~ Done: both now call `GameTracker.end_hand_from_result()`, which is the seed of the `RoundRecorder` below.

**Target:** `gin_rummy/tracking.py` with a `RoundRecorder` / `TrackingCallbacks` wrapping `GameTracker`, exposing `record_turn(...)`, `record_round(result: RoundResult)` and `record_draw()`.

### 2.3 A common `AIPlayer` protocol and AI factory
_Done (`06d3307`): BasicAI is the interface (uniform signatures, `needs_context`, tracking no-ops on the base class); `ai/factory.py` has `make_ai`, `AI_TYPES`, `DIFFICULTY_TO_AI`. No `isinstance`/`hasattr` gates remain in the runner, simulator, trainer or quiz._

There is no shared interface. Signatures differ (`context=`, `pending_discard=`), so callers use `isinstance`/`hasattr` about 15 times (`game_runner.py:92-291`, `simulator.py:359-633`, `trainer.py:346-620`, `scenario_quiz.py:226,279`). This caused B4.

- Define `AIPlayer` in `ai/types.py` with uniform signatures (context always optional) and no-op defaults for `update_context`, `record_opponent_*` and `reset_for_new_hand`.
- Move `update_context` / `record_opponent_*` / `reset_for_new_hand` (`context_aware.py:60-97` ≈ `learning_ai.py:95-136`) into the base class or an `OpponentTrackingMixin`.
- **Factory:** string→class mapping exists in `simulator.py:502-512`, `trainer.py:216-229` and `game_session.py:296-301, 359-364, 1055-1060`. Replace it with `AI_REGISTRY` / `make_ai()` in `ai/factory.py`, with a lazy import for `learning`.

### 2.4 Merge decision methods with their `_with_reasoning` twins
_Done (step 4): BasicAI uses `_evaluate_*` cores (no strings on the rollout path); ContextAwareAI's plain methods return the reasoning implementation's choice; StatisticalAI and LearningAI got their own twins (B8). `tests/test_reasoning_agreement.py` guards it._

`basic.py` and `context_aware.py` copy each decision body into a `_with_reasoning` twin: `context_aware.py:122-247 vs 574-694, 249-324 vs 696-782, 346-446 vs 784-870`, about 330 lines. MonteCarloAI already does it properly (`monte_carlo.py:1207-1311`): compute the reasoning once and have the plain method return `.choice`. Doing the same shrinks `context_aware.py` from ~870 to ~450 lines and fixes B8.

### 2.5 Card codec and shared hand helpers
_Card codec and index done (`f6aeb6b`, `37ec056`): `Card.code` / `Card.parse` / `Card.index` / `Card.from_index`, plus a process-stable `Card.__hash__`. The other rows below are still open._

| Duplicate | Locations | Target |
|---|---|---|
| Card ↔ `"7H"` string | `database.py:22-77`, `game_session.py:18-60`, `analyze_hand.py:23-54`, `scripts/stress_test_db.py:19-21` | `Card.code` / `Card.parse()` in `models/card.py` |
| Card → 0..51 index | `statistical.py:19-23`, `learning/state.py:28-32` (both O(n) `.index`) | `Card.index` |
| "Try each discard → deadwood" loop | `basic.py:150-156, 292-298`, `statistical.py:179-182`, `context_aware.py:157-159, 603-605`, `monte_carlo.py:141-145, 854-866`, `game_runner.py:160-171`, `cli.py:488-490`, `game_session.py:750-753` | `rank_discards()` / `Hand.deadwood_without(card)` in `models/` |
| Knock scoring | `monte_carlo.py:45-82` re-implements `game.py:454-493` | Pure `scoring.py` used by both |
| Known/unknown cards | `monte_carlo.py:660-684` vs `KnownCards` (`context.py:90-128`) | `KnownCards.unknown_cards` |
| Group by rank/suit | `melds.py:44-46, 73-75`, `context.py:477-505` | Helpers in `melds.py` |
| Game-over / target check | `simulator.py:330-343`, `game_session.py:978-1014` (the CLI never checks) | `Game.game_winner(target)` |
| Meld/hand JSON serialization | `game_session.py:521-526, 941-945`, `scenario_session.py:204-210`, `app.py:341-383` | `web/serializers.py` |
| Score SQL | `database.py:794-807`, `888-897` | `_hand_scores(conn, game_id)` |

### 2.6 Learning module internals
- Three identical MLP builders (`learning/models.py:20-124`): replace with one `MLPQNet(state_size, n_out, hidden)`. Also persist `hidden_sizes` in checkpoints (`models.py:177-183`).
- Three near-copy state encoders (`learning/state.py:170-243`): replace with one `_encode(...)`.
- Progress bar, `format_time` and logging setup are copied between `trainer.py:704-789` and `experiment.py:342-436`: move them to `learning/cli_utils.py`.

### 2.7 Frontend JS
- **Fetch:** `apiCall` (`game.js:535-556`) and `api` (`scenario.js:20-35`) duplicate each other, and there are raw `fetch` calls with no `ok` check (`game.js:617, 1528, 1545, 1697`, `history.js:76`). Replace with one `apiFetch`.
- **Card utilities:** `formatCardId` is redefined in `game.js:809-818`, shadowing `CardUtils`. Rank/suit lists are hard-coded again (`game.js:1011-1017`, `memory.js:3-4`). Symbol→letter conversion (`game.js:1003-1008`) is only needed because the API sends `str(c)` for `dead_cards`/`opponent_known` (`game_session.py:596-597`). Send IDs instead.
- **Meld-grouped hand rendering** is copied four times: `game.js:260-336`, `game.js:1077-1138`, `replay.js:37-93`, `scenario.js:80-120`.
- **Formatting:** relative time (`game.js:1586-1596`, `history.js:415-445`) and difficulty capitalization (5 places).
- **In `game.js`:** the "current human player name" block is copied three times (`:1671, 1706, 1734`), and building settings from localStorage is copied three times (`~:1361, 1412, 1628`).
- **Target:** grow `card-utils.js` into `shared/cards.js`, plus `shared/api.js` and `shared/format.js` (`relativeTime`, `capitalize`; `escapeHtml` now lives in `card-utils.js` and should move here too).

### 2.8 CSS
- About 910 lines of inline `<style>` sit in `history.html:9-394`, `memory.html:9-377` and `scenario.html:9-169`. Some of it conflicts with `style.css`: `.modal` z-index/background at `history.html:326-350` vs `style.css:679-700`. `.filter-btn`, `.thinking` and `.back-to-game` are also duplicated.
- There are no CSS custom properties: about 160 hex literals (`#4fc3f7` ×16, `#4caf50` ×15). Add `:root` tokens.
- There are no `@media` queries, so the pages have no mobile layout.

### 2.9 FastAPI routes (`app.py`)
- The `'error' in result → 400` block appears six times (`171-224`); `_scenario_result` (`552-555`) already does this. Use it everywhere, or raise `HTTPException` from the session.
- Cookie setting is duplicated (`41-47` vs `52-58`).
- Raw SQL sits in route handlers (`292-299, 443-494`), and the two history queries differ only in the WHERE clause. There are N+1 queries at `412` and `484-494`, plus `database.py:886-906`. Move it all into `database.py`.

---

## 3. Files that are too large

| File | Lines | Proposed split |
|---|---|---|
| `web/static/style.css` | 2109 | `base.css` (reset + `:root` tokens), `cards.css`, `board.css`, `modals.css`, `replay.css` (`:1399-2007`), plus `history.css` / `memory.css` / `scenario.css` extracted from the inline `<style>` blocks |
| `web/static/game.js` | 2058 | `state.js`, `api.js`, `settings.js`, `render/board.js`, `render/assist.js` (`:863-1056`), `render/modals.js`, `ai-playback.js`, `main.js`. Move to **ES modules** (`<script type="module">`, eslint `sourceType: "module"`) to drop the IIFEs; no bundler needed |
| `ai/monte_carlo.py` | 1311 | Package `ai/mc/`: `rollout.py` (1-274), `sampling.py` (288-323, 554-629), `workers.py` (pool + `_*_sim_batch`, collapsed to one), `thinking.py` (typed dataclasses in place of `dict[str, Any]`, plus formatters), `ai.py` (~300 lines of decision logic). Replace the 16-element positional task tuples with a frozen `SimParams` dataclass |
| `web/game_session.py` | 1072 | `web/serializers.py`, `web/assist.py` (`calculate_card_helpfulness`, `:71-165`), recording → shared recorder (§2.2), `GameSession` keeps only flow |
| `cli.py` | 965 | `cli/render.py` (display, ANSI), `cli/prompts.py` (input loops; the `q` handling is copied at `:347, 414, 454`), `cli/app.py` (`main`); the round loop moves to `engine/round_runner.py` |
| `database.py` | 951 | `db/schema.py` + `db/migrations.py` (numbered list), `db/tracker.py` (`GameTracker`), `db/queries.py`; serialization → `models/` |
| `ai/context_aware.py` | 870 | ~450 after §2.4 alone |
| `context.py` | 804 | `models/game_context.py` (`KnownCards`, `GameContext`), `ai/outs.py`, `ai/opponent_model.py`, `ai/thresholds.py`. This keeps AI heuristics out of the domain layer |
| `learning/trainer.py` | 799 | Reuse the round runner with an experience hook; move CLI glue to `cli_utils.py` |
| `simulator.py` | 644 | `simulator/metrics.py`, `simulator/runner.py`; the factory → `ai/factory.py` |
| `web/app.py` | 606 | `APIRouter`s: `routes/game.py`, `history.py`, `stats.py`, `scenario.py`, `pages.py`, with session injected via `Depends(get_session)` |
| `web/static/replay.js` | 651 | `HandReplay` is a single ~550-line class; split rendering from playback control |

**Longest functions**, in approximate lines:
- `game.js init`: 255
- `MonteCarloAI.should_knock`: 192
- `execute_ai_turn` (`game_runner.py:174`): 185
- `MonteCarloAI.decide_discard`: 175
- `renderGameState`: 165
- `Trainer._play_round`: 163
- `play_human_turn` (`cli.py:385`): 160
- `experiment.create_parser`: 154
- `trainer.main`: 140
- `memory.js submitAnswer`: 135
- `showRoundResult`: 128
- `simulator.main`: 125
- `update_player_stats`: 120
- `_find_partial_outs`: 120
- `GameSession.discard`: 120

---

## 4. Architecture and best practices

### Layering and global state
- The domain reads global config: `game.py:71-75, 178`. It also builds AI context (`game.py:167`), and `Card.colored_str` puts ANSI codes in the model (`card.py:92`). Instead, pass rules into `Game` and move presentation to the UIs.
- `scenario_quiz.py:23` imports a UI helper from `cli`, and `game_runner.py:9-12` depends on concrete AI classes.
- Singletons: `_config` (`config.py:436-451`), `_assist_show_values` (`cli.py:44`), `_LearningAI` (`simulator.py:13-22`). Constructors fall back to `get_config()` (`basic.py:35`, `context_aware.py:50`, `monte_carlo.py:494`), so tests depend on hidden state.

### Randomness and reproducibility
- Everything uses the global `random` module. MC sampling shares the RNG stream with the deck shuffle, so `experiments/sim_budget.py`'s "same seed" comparison doesn't produce identical deals across sim counts.
- Workers reseed from pid+time (`monte_carlo.py:282-285`).
- The trainer and experiment runner have no `--seed`.
- **Hash-order dependence is possible and unguarded.** `Card` hashes its `Rank`/`Suit` enums, which hash by name string, so set-of-cards iteration order changes per process unless `PYTHONHASHSEED` is fixed. A seeded 30-game Basic vs ContextAware run was still identical across two unpinned processes (2026-09-28), so no current tie-break is known to depend on it. But any AI that picks the first of several equal options while iterating a card set would silently break `--seed` reproducibility. Pin `PYTHONHASHSEED=0` for benchmark and fingerprint runs, or give `Card` a stable `__hash__` (e.g. from `Card.index` once §2.5 lands).
- **Fix:** inject a `random.Random` into `Deck`, `Game` and each AI, pass derived seeds to workers, and add `seed` to `TrainingConfig`.

### Config
- `config/learning.toml` is **never loaded**: `Config._from_data` has no section for it (`config.py:320-340`). (`config/network.toml` was deleted with `network/`.)
- Three sources disagree on the AI knock defaults: `config.py:36-37`, `config/ai.toml:12,17` and `config.toml.example:59,64`. The example is also missing `[monte_carlo_ai]`.
- Unknown keys crash `_from_data` but are silently dropped by `with_overrides` (`:413-416`). `with_overrides` reloads from disk instead of the active config (`:398`).
- Strategy strings aren't validated: an unknown `sample_strategy` silently becomes "independent" (`monte_carlo.py:767`). Use `Enum`/`Literal` types.
- Move magic numbers into config or named constants:
  - `context_aware.py:415-442` (0.5/0.3/0.2/15), meld-break penalty 100, gin EV 25 (should be `gin_bonus`)
  - `statistical.py:191-199`
  - `cli.py:854` (`25`)
  - `scenario_quiz.py:398` (8 workers)

### Web server
- ~~**Blocking work in `async def` routes.**~~ Done: the game and scenario routes are plain `def` (threadpool) and hold a per-session lock.
- **Process pool lifecycle** (_corrected 2026-09-28; see "Next up" A at the top_). Pools don't currently leak, because `__del__` runs on refcount drop. But that cleanup is fragile, a new 15-process pool starts every hand, and nothing caps processes across sessions. `ScenarioSession.shutdown` is never called, and session expiry just drops references. Fix: one shared app-level pool, `GameSession.close()` on eviction and on lifespan exit, and keep the AI across hands.
- There is no cap on session count; every cookieless request creates a 4-hour session (`app.py:51`).
- **Missing API validation:**
  - No Pydantic `response_model`s, and `/api/game/state` returns 200 with an `{'error'}` body.
  - Input types are too loose: `source` should be `Literal["deck","discard"]`, since anything else silently means deck (`game_session.py:669-676`). `target_score`, `player_name` and `/api/history?limit=` are unbounded.
- Destructive and debug endpoints have no auth (`DELETE /api/stats/{name}`, `DELETE /api/games/{id}`, `POST /api/admin/cleanup`, `GET /log/{level}`). That's fine for localhost; gate them behind a flag if the app is ever exposed.
- `get_state` recomputes helpfulness (about 104 `analyze_hand` calls) on every response, even with assist off (`game_session.py:571`).
- Static assets have unversioned URLs (`index.html:321-323`). Add `?v=<hash>` so browsers don't mix old and new JS/CSS.

### Frontend state
- `game.js` has about 12 mutable globals.
- Draw, discard and AI-turn have no in-flight guard, so a double-click can fire duplicate POSTs. `scenario.js:37-56` already has a `busy` flag; copy that.
- Dead knock-confirm flow: `pendingDiscardCard` is never set, so ~~`knock()` (`game.js:707`)~~ (removed in `3b8bfb5`, along with the unused `getState()`), the modal, `style.css:764-808`, `/api/game/knock` (`app.py:187-194`) and `GameSession.knock` are all unused.

### Database
- Every write opens a new connection (`database.py:283, 383, 411`), and `end_hand` + `update_player_stats` run in separate transactions (`:348-365`).
- `PRAGMA foreign_keys` is off, so `delete_game` cascades by hand (`:716-764`). Migrations swallow `OperationalError` (`:222-233`).
- `'Computer'` is hard-coded in SQL (`:656-673`) and in the web layer (`game_session.py:985`).
- The DB path is relative to the working directory, and there is already a stray `gin_rummy/game_history.db`. Resolve it against the project root or a user data directory.

### Performance
- The MC heuristic fallback calls `BasicAI._card_helps_hand`, which calls `self.decide_discard`, which is the *full MC discard* (`basic.py:107`). `decide_discard` also runs `super().decide_discard` every time just for a tie check (`monte_carlo.py:971`).
- `BasicAI.decide_discard` (used in rollouts, millions of calls) builds debug log strings eagerly (`basic.py:57-61, 160-163`). Guard them with `logger.isEnabledFor`.
- `find_all_melds(hand)` is recomputed inside a 52×melds loop (`context.py:274`).
- The trainer reloads the opponent checkpoint from disk every self-play episode (`trainer.py:208, 222`). `ReplayBuffer.sample` copies the whole deque on every call (`replay.py:89`).

### Logging
- `setup_logging` adds handlers on every call (`config.py:354-367`) and uses a plain `FileHandler`. `game.log` is currently **43 MB**. Switch to `RotatingFileHandler` and make setup idempotent.

### Dead code (remove)
- `cli.py`: `display_hand_with_melds` (`:105-164`) and the unused `human_player_idx` param (`:644`)
- `melds.py`: `_melds_overlap` (`:115`)
- `simulator.py`: `run_simulation` (`:453`)
- `monte_carlo.py`: `_sample_game_state` (`:686-721`)
- `DynamicThresholdCalculator` (built at `context_aware.py:55`, never used)
- `learning/state.py`: `index_to_card_tuple`, `get_card_indices`
- `learning/rewards.py`: `normalize_reward`
- Legacy `GameContext` fields (`context.py:146-149`)
- The knock-confirm flow above (JS entry point already gone; modal, CSS, route and `GameSession.knock` remain)
- ~~`network/` (§1)~~ done

---

## 5. Tests

- ~~**There is no `tests/conftest.py`.**~~ Done (`f68eb01`): `tests/conftest.py` isolates the DB per test, and `tests/helpers.py` holds `make_ai_config`, `make_mc_config`, `make_context` and a `cards("7S 8S 9S KC")` builder. The three test files now import them; `test_context.py` still builds `GameContext(` by hand.
  - `make_test_config()` is copied in `test_ai.py:10`, `test_monte_carlo.py:15` and `test_mc_upgrades.py:17`.
  - `make_context()` is copied in `test_monte_carlo.py:35` and `test_mc_upgrades.py:42`, and `test_context.py` builds `GameContext(` by hand 11 times.
  - `Card(Rank.X, Suit.Y)` is written out about 830 times.
  - Add shared fixtures and a `cards("7S 8S 9S KC")` helper.
- **Files named after events instead of modules.** Merge `test_review_fixes.py` into `test_game.py`/`test_melds.py`/`test_context.py` and a new `test_statistical.py`. Merge `test_mc_upgrades.py` into `test_monte_carlo.py` and `test_4card_run.py` into `test_ai.py`.
- **Untested modules:** `simulator.py`, `analyze_hand.py`, `scenario_quiz.py`, all of `web/` except `scenario_session`, and `learning/experiment.py`. `cli.py`, `database.py`, `game_runner.py` and `learning/trainer.py` now have narrow regression tests for B2–B5 only. `test_learning.py` is skipped entirely without torch. Highest-value additions:
  1. ~~FastAPI `TestClient` game-flow tests (add `httpx` to dev deps).~~ Done: `tests/test_web_app.py` (new game, full round, recording, validation, history routes). Extend to resume, match mode and the scenario API before splitting `app.py`/`game_session.py`.
  2. `database.py` against a `tmp_path` DB. Started in `tests/test_database.py` (would have caught B3); extend to `GameTracker.update_player_stats`, `delete_game`, `get_incomplete_games`.
  3. A 3-game `Simulator` smoke test.
  4. ~~A round-recording test for the CLI. This would have caught B2.~~ Done: `tests/test_cli.py`.

---

## 6. Tooling and repo hygiene

- ~~**No CI.**~~ Done (`72c06c3`): `.github/workflows/ci.yml` runs `uv sync --all-extras`, `ruff check`, `ruff format --check`, `pytest` and `npm run lint`; `.pre-commit-config.yaml` has ruff and ruff-format. First two runs passed; eslint is at 0 warnings as of `3b8bfb5`.
- **Ruff:** ~~run `ruff check --fix` and `ruff format` once, then list that commit in `.git-blame-ignore-revs`.~~ Done (`0b76869`, listed in `.git-blame-ignore-revs`). Still to do: extend `select` beyond `F,E,W` with `I, UP, B, SIM` (101 hits at audit time; **65 as of `6bef1bc`**, see "Next up" 0 at the top), and optionally `RUF, PT, PERF`.
- **ty:** 79 diagnostics (63 as of `8c65454`). The meaningful ones are `object` not callable from loosely typed dicts (`simulator.py:360-450`, `trainer.py:347-622`) and `BasicAI` has no `update_context` (`scenario_quiz.py:227-279`); both go away with §2.3. Add a `[tool.ty]` section.
- ~~**Pytest:** add `addopts = "-ra --strict-markers"` and a `learning` marker so the torch skip is visible.~~ Done, including the `pytestmark` in `test_learning.py`.
- **Dependencies:** `fastapi`/`uvicorn` are an optional `web` extra, but the web UI is the primary interface; consider making them core. ~~Add `httpx` and `pytest-cov` to dev.~~ Done.
- **pyproject metadata:** `readme`, `license` and `authors` are missing.
- **Layout:**
  - `scripts/stress_test_db.py` uses a `sys.path` hack and writes `stress_test.db` to the repo root (now git-ignored as of `2c8224b`).
  - `experiments/` (ad-hoc benchmarks that read private attributes like `ai._turn_plan`) and `gin_rummy/learning/experiment.py` (a CLI) have confusingly similar names. Consider renaming `experiments/` to `benchmarks/` and adding a short README.
- **Generated artifacts in git:** `docs/learning-ai.pdf` and `gin_rummy/READING_ORDER.pdf` duplicate their `.md` sources, and the second one ships inside the wheel. Remove both and generate on demand. Decide whether `models/statistical_ai_backup.json` (tracked) or `statistical_ai.json` (ignored) is the canonical one.
- **Local clutter** (ignored, but worth cleaning): `game.log` (43 MB), `.coverage`, `gin_rummy/game_history.db`, `models/experiments/` (3.6 MB).

### Docs
- **README:**
  - Missing `gin-scenario`, `gin-experiment` and the scenario page.
  - The "AI Types" list omits `statistical` and `montecarlo`.
- **`gin_rummy/READING_ORDER.md`:** it never mentions MC, the scenario quiz or `web/`. Update it and move it to `docs/`.
- **`config/overrides/README.md`:** documents only 5 of the 10 overrides.
- **Overlapping result docs:** `docs/context-ai-improvement-plan.md` (outdated ~53% figure), `docs/ai-tournament.md`, `SIMULATION_HISTORY.md` and the TODO roadmap all track results. Consolidate them into SIMULATION_HISTORY and archive the plan. Mark `docs/web_ui_spec.md` as historical.
- **TODO.md** (384 lines, 101 checked vs 23 open): delete the completed sections and the changelog (git already has them). Consider moving the open items to GitHub issues.

---

## Suggested order of work

1. ~~**Quick fixes:** B1 decision (delete `network/`), B2, B3, B4, B5, B6. Add tests for each as you go.~~ Done 2026-09-28.
2. ~~**Safety net:** CI + pre-commit, a one-time `ruff --fix` + `ruff format`, `conftest.py`, web `TestClient` and DB tests.~~ Done 2026-09-28.
3. ~~**First:** fix the B7 regression (two lines plus a test). Optional: a CPU-only torch index for CI.~~ Done 2026-09-28.
4. ~~**Consolidate the core:** card codec (§2.5), `AIPlayer` protocol + factory (§2.3), shared recorder (§2.2), reasoning twins (§2.4).~~ Done 2026-09-28, one commit per step, each verified against `scripts/fingerprint.py` (seeded per-game hashes, unchanged throughout) and the twin-agreement test.
5. ~~**Expand the ruff rules** ("Next up" 0 at the top)~~ Done 2026-09-28.
6. ~~**MC worker-pool lifecycle and blocking web routes** ("Next up" A at the top).~~ Done 2026-09-28.
7. **Round runner (§2.1):** approach (b) from "Next up" B: a blocking runner for CLI, simulator, quiz and trainer, with the web staying request-driven. Add the quiz and trainer fingerprints first.
8. **Split the large files (§3):** `monte_carlo.py`, `game_session.py`/`app.py`, `database.py`, `cli.py`, `context.py`.
9. **Frontend:** shared JS modules + ES modules, split `game.js`, extract CSS with `:root` tokens.
10. **Docs and TODO cleanup.**
