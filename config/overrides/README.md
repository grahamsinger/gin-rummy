# Config Overrides

Override files for testing different AI configurations in simulations.

## Usage

```bash
# Test aggressive vs conservative draw strategies
uv run python -m gin_rummy.simulator -n 200 -s 42 \
  --ai1-type context --ai1-config config/overrides/aggressive-draw.toml \
  --ai2-type context --ai2-config config/overrides/conservative-draw.toml

# Test knock strategies
uv run python -m gin_rummy.simulator -n 200 -s 42 \
  --ai1-type basic --ai1-config config/overrides/aggressive-knock.toml \
  --ai2-type basic --ai2-config config/overrides/conservative-knock.toml
```

## Available Overrides

| File | Description |
|------|-------------|
| `aggressive-draw.toml` | Low draw threshold (1), high key out bonus (3) |
| `conservative-draw.toml` | High draw threshold (5), low key out bonus (1) |
| `aggressive-knock.toml` | Knock whenever possible (deadwood <= 10) |
| `conservative-knock.toml` | Only knock at very low deadwood (<= 3) |
| `no-bonuses.toml` | Disable all bonuses, pure deadwood minimization |

## Creating Your Own

Override files only need to include the values you want to change.
All other values use the defaults from `config/`.

Example:
```toml
# my-custom-config.toml
[context_aware_ai]
base_draw_threshold = 4
```
