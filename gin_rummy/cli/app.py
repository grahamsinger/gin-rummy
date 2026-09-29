"""Terminal entry point: rules banner, mode and names, then rounds until the players stop."""

from __future__ import annotations

from pathlib import Path

from gin_rummy.ai import ContextAwareAI
from gin_rummy.cli.render import clear_screen
from gin_rummy.cli.round import play_round_pvp, play_round_vs_ai
from gin_rummy.config import load_config
from gin_rummy.db import GameTracker
from gin_rummy.game import Game


def main() -> None:
    """Main entry point for the CLI game."""
    # Load config and set up logging
    config = load_config()
    config.setup_logging()

    rules = config.game_rules

    clear_screen()
    print("=" * 50)
    print("         WELCOME TO GIN RUMMY")
    print("=" * 50)
    print("\nRules:")
    print(f"- Knock with {rules.knock_threshold} or less deadwood")
    print(f"- Gin (0 deadwood) = {rules.gin_bonus} bonus + opponent's deadwood")
    print(f"- Undercut = {rules.undercut_bonus} bonus + difference")
    print("- Type 'q' at any prompt to quit")

    # Game mode selection
    print("\nGame Mode:")
    print("  [1] Play vs AI")
    print("  [2] Play vs Human (local)")

    while True:
        mode = input("\nYour choice: ").strip()
        if mode in ("1", "2"):
            break
        print("Please enter 1 or 2")

    vs_ai = mode == "1"

    # Get player name(s)
    print()
    p1_name = input("Your name: ").strip() or "Player"

    if vs_ai:
        p2_name = "Computer"
        ai = ContextAwareAI()
        human_player_idx = 0
    else:
        p2_name = input("Player 2 name: ").strip() or "Player 2"
        ai = None
        human_player_idx = None

    game = Game(p1_name, p2_name)

    # Initialize game tracker if database tracking is enabled
    tracker: GameTracker | None = None
    if config.database.enabled:
        tracker = GameTracker(db_path=Path(config.database.path))
        tracker.start_game(p1_name, p2_name)

    while True:
        if vs_ai:
            assert ai is not None and human_player_idx is not None
            play_round_vs_ai(game, ai, human_player_idx, tracker)
        else:
            play_round_pvp(game, tracker)

        # Ask to play another round
        choice = input("\nPlay another round? (y/n): ").strip().lower()
        if choice != "y":
            break

        game.new_round()

    # End game tracking
    if tracker:
        winner = max(game.players, key=lambda p: p.score)
        winner_name = winner.name if game.players[0].score != game.players[1].score else None
        tracker.end_game(winner_name=winner_name, score_p1=game.players[0].score, score_p2=game.players[1].score)

    print("\n" + "=" * 50)
    print("           FINAL SCORES")
    print("=" * 50)
    print(f"\n{game.players[0].name}: {game.players[0].score}")
    print(f"{game.players[1].name}: {game.players[1].score}")

    winner = max(game.players, key=lambda p: p.score)
    if game.players[0].score == game.players[1].score:
        print("\nIt's a tie!")
    else:
        print(f"\n{winner.name} wins!")

    print("\nThanks for playing!")


if __name__ == "__main__":
    main()
