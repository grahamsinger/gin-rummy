"""Terminal interface for Gin Rummy."""

import os
import sys
import time
from enum import Enum, auto

from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.config import get_config, load_config
from gin_rummy.game import Game, GamePhase, InvalidActionError
from gin_rummy.hand import Hand
from gin_rummy.melds import MeldType


class TurnResult(Enum):
    """Result of a turn."""

    CONTINUE = auto()  # Round continues
    KNOCKED = auto()  # Player knocked, round over
    DRAW = auto()  # Deck exhausted, round is a draw


def clear_screen() -> None:
    """Clear the terminal screen if enabled in config."""
    if get_config().display.clear_screen:
        os.system("cls" if os.name == "nt" else "clear")


def display_hand_with_melds(hand: Hand, show_numbers: bool = True, for_discard: bool = False) -> list:
    """Display a hand with melds visually grouped.

    Args:
        hand: The hand to display.
        show_numbers: If True, show card numbers for selection.
        for_discard: If True, order deadwood first for easier discard selection.

    Returns:
        List of cards in display order (for mapping selection numbers).
    """
    analysis = hand.analyze()

    # Build ordered card list: deadwood first if for_discard, otherwise original order
    if for_discard:
        # Deadwood cards first (sorted by value, highest first for easy discard)
        deadwood_sorted = sorted(analysis.deadwood_cards, key=lambda c: -c.deadwood_value)
        melded_cards = [c for c in hand if c not in analysis.deadwood_cards]
        display_cards = deadwood_sorted + melded_cards
    else:
        display_cards = list(hand)

    # Build a mapping from card to its meld (if any)
    card_to_meld: dict = {}
    for meld in analysis.melds:
        for card in meld.cards:
            card_to_meld[card] = meld

    # Display melds
    if analysis.melds:
        print("  Melds:")
        for meld in analysis.melds:
            meld_type = "Set" if meld.meld_type == MeldType.SET else "Run"
            cards_str = " ".join(str(c) for c in meld.cards)
            print(f"    [{meld_type}] {cards_str}")

    # Display deadwood summary
    if analysis.deadwood_cards:
        deadwood_str = " ".join(str(c) for c in sorted(analysis.deadwood_cards, key=lambda c: -c.deadwood_value))
        print(f"  Deadwood ({analysis.deadwood_value}): {deadwood_str}")
    else:
        print("  Deadwood (0): None - GIN!")

    # Display all cards with numbers for selection
    if show_numbers:
        if for_discard:
            print("\n  Choose card to discard (deadwood listed first):")
        else:
            print("\n  All cards:")

        for i, card in enumerate(display_cards, 1):
            marker = "*" if card in card_to_meld else " "
            print(f"  {i:2}.{marker}{card}", end="")
            if i % 5 == 0:
                print()
        if len(display_cards) % 5 != 0:
            print()
        print("  (* = in a meld)")

    return display_cards


def display_game_state(game: Game, human_player_idx: int, show_opponent: bool = False) -> None:
    """Display the current game state from human player's perspective.

    Args:
        game: The game instance.
        human_player_idx: Index of the human player (0 or 1).
        show_opponent: If True, show opponent's cards (for debugging).
    """
    human = game.players[human_player_idx]
    opponent = game.players[1 - human_player_idx]

    print("\n" + "=" * 50)
    print("              GIN RUMMY")
    print("=" * 50)

    # Scores
    print(f"\nScores: {human.name}: {human.score}  |  "
          f"{opponent.name}: {opponent.score}")

    # Opponent info
    print(f"\n{opponent.name} has {len(opponent.hand)} cards")
    if show_opponent:
        opponent.hand.sort()
        print(f"  (DEBUG: {opponent.hand})")

    print(f"Deck: {len(game.deck)} cards")

    # Discard pile
    if game.top_of_discard:
        print(f"Discard pile: {game.top_of_discard}")
    else:
        print("Discard pile: (empty)")

    # Human player's hand with meld analysis
    human.hand.sort()
    print(f"\n{human.name}'s hand:")
    display_hand_with_melds(human.hand)

    print()


def get_card_choice(hand: Hand, prompt: str) -> int:
    """Get a valid card index from user input.

    Args:
        hand: The hand to choose from.
        prompt: Prompt to display.

    Returns:
        0-based index of chosen card.
    """
    hand_size = len(hand)
    while True:
        try:
            choice = input(prompt)
            if choice.lower() == "q":
                print("Thanks for playing!")
                sys.exit(0)
            idx = int(choice)
            if 1 <= idx <= hand_size:
                return idx - 1
            print(f"Please enter a number between 1 and {hand_size}")
        except ValueError:
            print("Please enter a valid number")


def play_human_first_discard(game: Game, human_player_idx: int) -> None:
    """Handle human player's opening discard."""
    display_game_state(game, human_player_idx)
    print(f"{game.current_player.name}, discard one card to start the game.")
    idx = get_card_choice(game.current_player.hand, "Card to discard (1-11): ")
    card = game.current_player.hand[idx]
    game.discard_to_start(card)
    print(f"\nDiscarded {card}")


def play_ai_first_discard(game: Game, ai: BasicAI) -> None:
    """Handle AI's opening discard."""
    delay = get_config().display.ai_turn_delay
    print(f"\n{game.current_player.name} is choosing a card to discard...")
    time.sleep(delay * 2)  # Slightly longer for first discard

    discard = ai.decide_discard(game.current_player.hand)
    game.discard_to_start(discard)
    print(f"{game.current_player.name} discarded {discard}")
    time.sleep(delay)


def play_human_turn(game: Game, human_player_idx: int) -> TurnResult:
    """Play a human player's turn.

    Returns:
        TurnResult indicating whether round continues, ended by knock, or draw.
    """
    clear_screen()
    display_game_state(game, human_player_idx)

    current = game.current_player
    print(f"{current.name}'s turn")

    # Drawing phase
    print("\nDraw from:")
    print("  [1] Deck")
    if game.top_of_discard:
        print(f"  [2] Discard pile ({game.top_of_discard})")

    while True:
        choice = input("\nYour choice: ").strip()
        if choice == "q":
            print("Thanks for playing!")
            sys.exit(0)

        if choice == "1":
            try:
                card = game.draw_from_deck()
                print(f"\nDrew {card} from deck")
                break
            except InvalidActionError as e:
                print(f"\n{e}")
                return TurnResult.DRAW
        elif choice == "2" and game.top_of_discard:
            card = game.draw_from_discard()
            print(f"\nPicked up {card} from discard")
            break
        else:
            print("Invalid choice")

    # Update display after drawing - show cards ordered for discard
    current.hand.sort()
    print(f"\nYour hand:")
    display_cards = display_hand_with_melds(current.hand, for_discard=True)

    # Discard phase (with optional knock)
    if game.can_knock:
        print(f"\n  [K] Knock! (deadwood: {current.hand.deadwood_total})")

    while True:
        prompt = "Card # to discard (or 'k' to knock): " if game.can_knock else "Card # to discard: "
        choice = input(f"\n{prompt}").strip().lower()

        if choice == "q":
            print("Thanks for playing!")
            sys.exit(0)

        if choice == "k" and game.can_knock:
            result = game.knock()
            display_round_result(game)
            return TurnResult.KNOCKED

        # Try to parse as card number
        try:
            idx = int(choice)
            if 1 <= idx <= len(display_cards):
                discard_card = display_cards[idx - 1]
                game.discard(discard_card)
                print(f"\nDiscarded {discard_card}")
                return TurnResult.CONTINUE
            print(f"Please enter a number between 1 and {len(display_cards)}")
        except ValueError:
            if game.can_knock:
                print("Enter a card number or 'k' to knock")
            else:
                print("Please enter a valid card number")


def play_ai_turn(game: Game, ai: BasicAI, human_player_idx: int) -> TurnResult:
    """Play an AI turn.

    Returns:
        TurnResult indicating whether round continues, ended by knock, or draw.
    """
    delay = get_config().display.ai_turn_delay
    current = game.current_player
    print(f"\n{current.name}'s turn...")
    time.sleep(delay)

    # AI decides where to draw
    draw_choice = ai.decide_draw(current.hand, game.top_of_discard)

    if draw_choice == DrawChoice.DISCARD and game.top_of_discard:
        card = game.draw_from_discard()
        print(f"{current.name} picked up {card} from discard pile")
    else:
        try:
            card = game.draw_from_deck()
            print(f"{current.name} drew from deck")
        except InvalidActionError:
            # Deck exhausted
            return TurnResult.DRAW

    time.sleep(delay)

    # AI decides what to discard and whether to knock
    discard, should_knock = ai.make_turn_decision(
        current.hand, game.top_of_discard, card
    )

    if should_knock and game.can_knock:
        print(f"{current.name} knocks!")
        time.sleep(delay)
        result = game.knock()
        display_round_result(game)
        return TurnResult.KNOCKED
    else:
        game.discard(discard)
        print(f"{current.name} discarded {discard}")
        time.sleep(delay)
        return TurnResult.CONTINUE


def display_round_result(game: Game) -> None:
    """Display the result of a round."""
    print("\n" + "=" * 50)
    print("           ROUND OVER")
    print("=" * 50)

    # Show both hands with melds
    for player in game.players:
        player.hand.sort()
        print(f"\n{player.name}'s hand:")
        display_hand_with_melds(player.hand, show_numbers=False)

    print()

    # Get result info from game state
    # Note: result is stored when knock() is called
    # For now, recalculate from hands
    p0_deadwood = game.players[0].hand.deadwood_total
    p1_deadwood = game.players[1].hand.deadwood_total

    print(f"{game.players[0].name}: {p0_deadwood} deadwood")
    print(f"{game.players[1].name}: {p1_deadwood} deadwood")

    print(f"\nScores: {game.players[0].name}: {game.players[0].score}  |  "
          f"{game.players[1].name}: {game.players[1].score}")


def play_round_vs_ai(game: Game, ai: BasicAI, human_player_idx: int) -> None:
    """Play a complete round against AI."""
    game.deal()

    # Determine who does first discard (non-dealer)
    non_dealer_idx = 1 - game.dealer_idx

    clear_screen()

    if non_dealer_idx == human_player_idx:
        # Human does first discard
        play_human_first_discard(game, human_player_idx)
    else:
        # AI does first discard
        display_game_state(game, human_player_idx)
        play_ai_first_discard(game, ai)

    input("\nPress Enter to continue...")

    # Main game loop
    turn_result = TurnResult.CONTINUE
    while game.phase not in (GamePhase.ROUND_OVER, GamePhase.KNOCKED):
        if game.current_player_idx == human_player_idx:
            turn_result = play_human_turn(game, human_player_idx)
            if turn_result != TurnResult.CONTINUE:
                break
        else:
            clear_screen()
            display_game_state(game, human_player_idx)
            turn_result = play_ai_turn(game, ai, human_player_idx)
            if turn_result != TurnResult.CONTINUE:
                break
            input("\nPress Enter to continue...")

    if turn_result == TurnResult.DRAW:
        print("\nRound ended in a DRAW (deck exhausted)")

    input("\nPress Enter to continue...")


def play_round_pvp(game: Game) -> None:
    """Play a complete round player vs player."""
    game.deal()

    # First discard
    clear_screen()
    display_game_state(game, game.current_player_idx)
    print(f"{game.current_player.name}, discard one card to start the game.")
    idx = get_card_choice(game.current_player.hand, "Card to discard (1-11): ")
    card = game.current_player.hand[idx]
    game.discard_to_start(card)
    print(f"\nDiscarded {card}")

    input("\nPress Enter for next player's turn...")

    # Main game loop
    turn_result = TurnResult.CONTINUE
    while game.phase not in (GamePhase.ROUND_OVER, GamePhase.KNOCKED):
        turn_result = play_human_turn(game, game.current_player_idx)
        if turn_result != TurnResult.CONTINUE:
            break
        if game.phase not in (GamePhase.ROUND_OVER, GamePhase.KNOCKED):
            input("\nPress Enter for next player's turn...")

    if turn_result == TurnResult.DRAW:
        print("\nRound ended in a DRAW (deck exhausted)")

    input("\nPress Enter to continue...")


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
        ai = BasicAI()
        human_player_idx = 0
    else:
        p2_name = input("Player 2 name: ").strip() or "Player 2"
        ai = None
        human_player_idx = None

    game = Game(p1_name, p2_name)

    while True:
        if vs_ai:
            assert ai is not None and human_player_idx is not None
            play_round_vs_ai(game, ai, human_player_idx)
        else:
            play_round_pvp(game)

        # Ask to play another round
        choice = input("\nPlay another round? (y/n): ").strip().lower()
        if choice != "y":
            break

        game.new_round()

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
