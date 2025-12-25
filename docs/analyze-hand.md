# Analyze Hand Tool

A command-line tool for analyzing a gin rummy hand and calculating outs.

## Usage

```bash
uv run python -m gin_rummy.analyze_hand "<hand>" [options]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `hand` | Space-separated card codes (required) |
| `--dead`, `-d` | Buried discard pile cards |
| `--opponent`, `-o` | Cards known to be in opponent's hand (picked from discard) |
| `--discard-top`, `-t` | Current top card of discard pile |

### Card Format

Cards are specified as `<rank><suit>`:
- **Ranks:** A, 2-9, T (ten), J, Q, K
- **Suits:** S (spades), H (hearts), D (diamonds), C (clubs)

Examples: `AS` (Ace of Spades), `TH` (Ten of Hearts), `KD` (King of Diamonds)

## Output Sections

1. **Hand** - Your cards organized by suit
2. **Melds & Deadwood** - Current meld count and deadwood value
3. **Card Locations** - Breakdown of where all cards are located
4. **Meld-Completing Outs** - Cards that would complete a 3+ card meld
5. **Partial Outs** - Cards that build toward melds (pairs, run extensions)
6. **Summary** - Live/dead out counts and weighted value

## Example

```bash
uv run python -m gin_rummy.analyze_hand "3S 8S 2H 2D 3D 6D KD 6C 8C KC" \
  --dead "AS JS QC" --opponent "2C 5H" --discard-top "7S"
```

Output:
```
============================================================
HAND ANALYSIS
============================================================

Hand:
  ♠: 3♠ 8♠
  ♥: 2♥
  ♦: 2♦ 3♦ 6♦ K♦
  ♣: 6♣ 8♣ K♣

Current melds: 0
Deadwood: 58
Deadwood cards: ['3♠', '8♠', '2♥', '2♦', '3♦', '6♦', 'K♦', '6♣', '8♣', 'K♣']

------------------------------------------------------------
CARD LOCATIONS
------------------------------------------------------------
  My hand: 10 cards
  Opponent known: 2 cards - ['2♣', '5♥']
  Discard top: 7♠
  Discard buried: 3 cards - ['A♠', 'J♠', 'Q♣']
  Unknown: 36 cards (in deck or opponent's initial hand)
  Dead cards: 5 (opponent known + buried)

------------------------------------------------------------
MELD-COMPLETING OUTS
------------------------------------------------------------
  A♦: completes run: A♦ 2♦ 3♦
  2♣: completes set: 2♣ 2♦ 2♥ [DEAD]
  2♠: completes set: 2♦ 2♥ 2♠
  3♣: completes set: 3♣ 3♦ 3♠
  3♥: completes set: 3♦ 3♥ 3♠
  4♦: completes run: 2♦ 3♦ 4♦
  6♥: completes set: 6♣ 6♦ 6♥
  6♠: completes set: 6♣ 6♦ 6♠
  7♣: completes run: 6♣ 7♣ 8♣
  8♦: completes set: 8♣ 8♦ 8♠
  8♥: completes set: 8♣ 8♥ 8♠
  K♥: completes set: K♣ K♦ K♥
  K♠: completes set: K♣ K♦ K♠

------------------------------------------------------------
PARTIAL OUTS (set-building, run-extending)
------------------------------------------------------------
  A♦ (RUN_EXTENDING): extends 2♦-3♦ run
  2♣ (SET_BUILDING): extends pair of 2s to set [DEAD]
  2♠ (SET_BUILDING): extends pair of 2s to set
  3♣ (SET_BUILDING): extends pair of 3s to set
  3♥ (SET_BUILDING): extends pair of 3s to set
  4♦ (RUN_EXTENDING): extends 2♦-3♦ run
  6♥ (SET_BUILDING): extends pair of 6s to set
  6♠ (SET_BUILDING): extends pair of 6s to set
  7♣ (RUN_EXTENDING): fills gap between 6♣ and 8♣
  8♦ (SET_BUILDING): extends pair of 8s to set
  8♥ (SET_BUILDING): extends pair of 8s to set
  K♥ (SET_BUILDING): extends pair of Ks to set
  K♠ (SET_BUILDING): extends pair of Ks to set

------------------------------------------------------------
SUMMARY
------------------------------------------------------------
  Meld-completing outs: 13
  Partial outs: 13
  Total live outs: 24
  Dead outs: 2
  Weighted value: 273.0
```

Note how `2♣` is marked `[DEAD]` because the opponent picked it up from the discard pile.
