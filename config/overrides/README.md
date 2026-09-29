# Config Overrides

Override files for comparing AI configurations in the simulator. Each file only
contains the values it changes; everything else comes from `config/`.

## Usage

```bash
# Aggressive vs conservative draw thresholds (ContextAwareAI)
uv run gin-simulate -n 200 -s 42 \
  --ai1-type context --ai1-config config/overrides/aggressive-draw.toml \
  --ai2-type context --ai2-config config/overrides/conservative-draw.toml

# Knock strategies (BasicAI)
uv run gin-simulate -n 200 -s 42 \
  --ai1-type basic --ai1-config config/overrides/aggressive-knock.toml \
  --ai2-type basic --ai2-config config/overrides/conservative-knock.toml

# Monte Carlo A/B: upgrades on vs off at identical simulation counts
uv run gin-simulate -n 20 -s 101 -t 50 \
  --ai1-type montecarlo --ai1-config config/overrides/mc-bench-new.toml \
  --ai2-type montecarlo --ai2-config config/overrides/mc-bench-legacy.toml
```

## Available Overrides

| File | Section | What it changes |
|------|---------|-----------------|
| `aggressive-draw.toml` | `[context_aware_ai]` | `base_draw_threshold = 1`: take cards from the discard pile more readily |
| `conservative-draw.toml` | `[context_aware_ai]` | `base_draw_threshold = 5`: be more selective |
| `aggressive-knock.toml` | `[ai]` | `knock_strategy = "always"`: knock whenever legal |
| `conservative-knock.toml` | `[ai]` | `knock_strategy = "conservative"` with threshold 3 |
| `gin_hunter.toml` | `[ai]` | Conservative threshold 0 (only knocks with gin) and `min_deadwood_improvement = 0` |
| `flat-knock.toml` | `[context_aware_ai]` | `use_phased_knock = false` |
| `phased-knock.toml` | `[context_aware_ai]` | `use_phased_knock = true` (results in `SIMULATION_HISTORY.md`, 2026-02-11) |
| `no-bonuses.toml` | `[context_aware_ai]` | All discard bonuses and penalties zeroed: pure deadwood minimisation |
| `mc-bench-new.toml` | `[monte_carlo_ai]` | 150 sims per decision, 1 worker, the 2026-07-12 upgrades **on** |
| `mc-bench-legacy.toml` | `[monte_carlo_ai]` | Same sims and workers, upgrades **off** (pair with the above) |

## Creating Your Own

```toml
# my-custom-config.toml
[context_aware_ai]
base_draw_threshold = 4
```

Section and key names are the same as in the files under `config/`.
