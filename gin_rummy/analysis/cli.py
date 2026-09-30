"""gin-analyze: deep analysis of one decision, saved to the database.

Usage:
    uv run gin-analyze --seed 20587                  # the discard, after drawing from the deck
    uv run gin-analyze --seed 20587 --draw pile      # the discard, after taking the face-up card
    uv run gin-analyze --seed 20587 --decision draw
    uv run gin-analyze --seed 20587 --decision knock --discard 5S
    uv run gin-analyze --list
    uv run gin-analyze --show 3

A position that has been analysed before is shown from the database;
--force analyses it again."""

from __future__ import annotations

import argparse
import sys

from gin_rummy.analysis.deep import Position, analyse, position_from_game
from gin_rummy.analysis.report import format_report, pretty
from gin_rummy.db.deep_analyses import find_deep_analysis, get_deep_analysis, list_deep_analyses, save_deep_analysis
from gin_rummy.models import Card
from gin_rummy.scenario.core import HUMAN_SEAT, build_panel, generate_stable_scenario


def scenario_position(seed: int, decision: str, draw: str = "deck", discard: str | None = None) -> Position:
    """The position a quiz scenario puts to the player at `decision`.

    draw: how the player drew ('deck' or 'pile'), for the discard and knock decisions.
    discard: the card thrown, for the knock decision.
    """
    game = generate_stable_scenario(seed, build_panel(1, 1))
    if game is None:
        raise ValueError(f"Seed {seed} does not produce a scenario")
    if decision == "draw":
        return position_from_game(game, HUMAN_SEAT, "draw", seed)
    if draw == "pile":
        game.draw_from_discard()
    else:
        game.draw_from_deck()
    if decision == "discard":
        return position_from_game(game, HUMAN_SEAT, "discard", seed)
    if discard is None:
        raise ValueError("The knock decision needs the card being discarded")
    card = Card.parse(discard.upper())
    if card not in game.players[HUMAN_SEAT].hand:
        raise ValueError(f"{card} is not in the hand")
    return position_from_game(game, HUMAN_SEAT, "knock", seed, pending_discard=card)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep analysis of one gin rummy decision")
    parser.add_argument("--seed", type=int, help="scenario seed, as shown on the quiz page")
    parser.add_argument("--decision", choices=["draw", "discard", "knock"], default="discard")
    parser.add_argument("--draw", choices=["deck", "pile"], default="deck", help="how you drew (default: deck)")
    parser.add_argument("--discard", help="the card thrown, for the knock decision (e.g. 5S)")
    parser.add_argument("--samples", type=int, default=20000, help="most deals to try (default: 20000)")
    parser.add_argument("--batch", type=int, default=2000, help="deals per round (default: 2000)")
    parser.add_argument("--workers", type=int, default=0, help="worker processes (default: all cores but one)")
    parser.add_argument("--force", action="store_true", help="analyse again even if a result is saved")
    parser.add_argument("--list", action="store_true", help="list saved analyses")
    parser.add_argument("--show", type=int, metavar="ID", help="show a saved analysis")
    args = parser.parse_args()

    if args.list:
        for row in list_deep_analyses(args.seed):
            print(
                f"{row['id']:>4}  {row['created_at'][:16]}  seed {row['seed']}  {row['decision']:<8}"
                f"best {pretty(row['best']):<9}{row['confidence']:<18}{row['samples']} deals"
            )
        return
    if args.show is not None:
        shown = get_deep_analysis(args.show)
        if shown is None:
            sys.exit(f"No saved analysis with id {args.show}")
        else:
            print(format_report(shown))
        return
    if args.seed is None:
        parser.error("--seed is required")

    try:
        position = scenario_position(args.seed, args.decision, args.draw, args.discard)
    except ValueError as error:
        sys.exit(str(error))

    saved = None if args.force else find_deep_analysis(position.key)
    if saved is not None:
        print(f"(saved analysis {saved['id']} from {saved['created_at'][:16]}; --force to run again)\n")
        print(format_report(saved))
        return

    result = analyse(
        position,
        max_samples=args.samples,
        batch=args.batch,
        workers=args.workers,
        progress=lambda message: print(message, flush=True),
    )
    analysis_id = save_deep_analysis(result)
    print()
    print(format_report(result))
    print(f"\nSaved as analysis {analysis_id}.")


if __name__ == "__main__":
    main()
