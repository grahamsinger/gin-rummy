"""gin-scenario: quiz yourself against the AIs on random positions in the terminal.

Usage:
    uv run gin-scenario                 # 3 scenarios, random seed
    uv run gin-scenario --count 5 --seed 42
    uv run gin-scenario --mc-sims 1000  # stronger (slower) MC advice"""

from __future__ import annotations

import argparse
import random
import sys

from gin_rummy.ai import DrawChoice, MonteCarloAI
from gin_rummy.cli.render import display_hand_by_suit
from gin_rummy.game import Game
from gin_rummy.game_runner import calculate_post_discard_deadwood
from gin_rummy.models import Card, Hand
from gin_rummy.scenario.core import (
    HUMAN_SEAT,
    PanelMember,
    build_panel,
    generate_stable_scenario,
    panel_discard_choices,
    panel_draw_choices,
    panel_knock_choices,
    split_opponent_pickups,
)


def show_position(game: Game) -> None:
    """Print the frozen position from the human's perspective."""
    ctx = game.get_game_context(HUMAN_SEAT)
    human = game.players[HUMAN_SEAT]
    analysis = human.hand.analyze()

    print("\n" + "=" * 62)
    print("SCENARIO")
    print("=" * 62)
    print("\nYour hand:")
    display_hand_by_suit(human.hand, show_numbers=False)
    if analysis.melds:
        print("Melds:    " + " | ".join(str(m) for m in analysis.melds))
    print(f"\nDiscard top:   {game.top_of_discard}")
    print(f"Deck remaining: {len(game.deck)}")

    held, returned = split_opponent_pickups(ctx)
    if held:
        print(f"Opponent holds:     {' '.join(str(c) for c in held)}")
    if returned:
        print(f"Opponent threw back: {' '.join(str(c) for c in returned)}")
    buried = sorted(ctx.dead_cards)
    if buried:
        print(f"Buried discards:    {' '.join(str(c) for c in buried)}")


def ask(prompt: str, valid: set[str]) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if answer == "q":
            print("\nQuiz ended.")
            sys.exit(0)
        if answer in valid:
            return answer
        print(f"Please enter one of: {', '.join(sorted(valid))} (or q to quit)")


def ask_draw(game: Game) -> DrawChoice:
    answer = ask(
        f"\nDraw from [d]eck or take {game.top_of_discard} from [p]ile? ",
        {"d", "p"},
    )
    return DrawChoice.DISCARD if answer == "p" else DrawChoice.DECK


def ask_discard(game: Game) -> Card:
    print("\nYour hand after drawing:")
    cards = display_hand_by_suit(game.players[HUMAN_SEAT].hand, show_numbers=True)
    while True:
        answer = input("\nCard # to discard: ").strip().lower()
        if answer == "q":
            print("\nQuiz ended.")
            sys.exit(0)
        try:
            idx = int(answer)
            if 1 <= idx <= len(cards):
                card = cards[idx - 1]
                if card == game.discard_blocked_card:
                    print(f"You can't discard {card} - you just took it from the pile.")
                    continue
                return card
        except ValueError:
            pass
        print(f"Enter a number 1-{len(cards)}")


def reveal_draw_choices(panel: list[PanelMember], game: Game, user_choice: DrawChoice) -> None:
    took = f"take {game.top_of_discard}" if user_choice == DrawChoice.DISCARD else "draw from deck"
    print(f"\nYou chose: {took}")
    print("-" * 62)
    for member, entry in zip(panel, panel_draw_choices(panel, game), strict=True):
        agrees = entry["choice"] == user_choice
        member.draw_agreements += agrees
        marker = "=" if agrees else "≠"
        print(f"  [{marker}] {member.name:<16} {entry['reasoning']}")


def reveal_discard_choices(panel: list[PanelMember], game: Game, user_card: Card) -> None:
    print(f"\nYou discarded: {user_card}")
    print("-" * 62)
    for member, entry in zip(panel, panel_discard_choices(panel, game), strict=True):
        agrees = entry["card"] == user_card
        member.discard_agreements += agrees
        marker = "=" if agrees else "≠"
        print(f"  [{marker}] {member.name:<16} {entry['reasoning']}")
        if entry["mc_candidates"]:
            top3 = entry["mc_candidates"][:3]
            evs = ", ".join(f"{c.card}: {c.avg_points:+.1f}" for c in top3)
            print(f"        MC EVs (top 3): {evs}")


def reveal_knock_choices(
    panel: list[PanelMember],
    game: Game,
    post_hand: Hand,
    pending: Card,
    user_knocks: bool,
) -> None:
    print(f"\nYou chose: {'KNOCK' if user_knocks else 'keep playing'}")
    print("-" * 62)
    for member, entry in zip(panel, panel_knock_choices(panel, game, post_hand, pending), strict=True):
        agrees = entry["knocks"] == user_knocks
        member.knock_agreements += agrees
        marker = "=" if agrees else "≠"
        print(f"  [{marker}] {member.name:<16} {entry['reasoning']}")


def run_scenario(seed: int, panel: list[PanelMember]) -> bool:
    """Run one scenario. Returns False if generation failed for this seed."""
    game = generate_stable_scenario(seed, panel)
    if game is None:
        return False

    show_position(game)

    # --- Decision 1: draw ---
    user_draw = ask_draw(game)
    reveal_draw_choices(panel, game, user_draw)

    drawn = game.draw_from_discard() if user_draw == DrawChoice.DISCARD else game.draw_from_deck()
    print(f"\nYou drew: {drawn}")

    # --- Decision 2: discard ---
    user_discard = ask_discard(game)
    reveal_discard_choices(panel, game, user_discard)

    # --- Decision 3: knock (only if eligible) ---
    human = game.players[HUMAN_SEAT]
    post_deadwood = calculate_post_discard_deadwood(human.hand, user_discard)
    if post_deadwood <= game.knock_threshold:
        answer = ask(
            f"\nDiscarding {user_discard} leaves {post_deadwood} deadwood. Knock? [y/n] ",
            {"y", "n"},
        )
        post_hand = Hand([c for c in human.hand if c != user_discard])
        reveal_knock_choices(panel, game, post_hand, user_discard, answer == "y")

    return True


def print_summary(panel: list[PanelMember], scenarios: int) -> None:
    print("\n" + "=" * 62)
    print(f"SESSION SUMMARY ({scenarios} scenario{'s' if scenarios != 1 else ''})")
    print("=" * 62)
    print(f"{'AI':<18} {'draw':>6} {'discard':>9} {'knock':>7}")
    for member in panel:
        print(
            f"{member.name:<18} {member.draw_agreements:>6} {member.discard_agreements:>9} {member.knock_agreements:>7}"
        )
    print("\n(counts = times the AI agreed with your choice)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quiz yourself against the AIs on random gin rummy scenarios")
    parser.add_argument("--count", type=int, default=3, help="Number of scenarios")
    parser.add_argument("--seed", type=int, default=None, help="Base RNG seed")
    parser.add_argument(
        "--mc-sims", type=int, default=500, help="MC simulations per decision (default 500: ~2-4s per answer)"
    )
    parser.add_argument(
        "--mc-workers", type=int, default=8, help="MC worker processes (8 saturates the useful parallelism)"
    )
    args = parser.parse_args()

    base_seed = args.seed if args.seed is not None else random.randrange(1_000_000)
    print(f"Gin Rummy scenario quiz (seed {base_seed}, q to quit at any prompt)")

    panel = build_panel(args.mc_sims, args.mc_workers)
    completed = 0
    for i in range(args.count):
        # run_scenario resets opponent tracking per attempt; tallies persist
        if run_scenario(base_seed + i, panel):
            completed += 1
        else:
            print(f"\n(scenario {i + 1}: could not generate a stable position, skipped)")

    if completed:
        print_summary(panel, completed)

    for member in panel:
        if isinstance(member.ai, MonteCarloAI):
            member.ai.shutdown()


if __name__ == "__main__":
    main()
