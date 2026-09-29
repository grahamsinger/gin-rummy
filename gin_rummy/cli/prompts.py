"""Terminal prompts: card choice, the opening discard and a human's turn."""

from __future__ import annotations

import sys

from gin_rummy.ai import DrawChoice
from gin_rummy.cli.render import (
    clear_screen,
    display_game_state,
    display_hand_by_suit,
    display_round_result,
    toggle_assist_values,
)
from gin_rummy.db import GameTracker
from gin_rummy.game import Game, InvalidActionError, RoundResult
from gin_rummy.game_runner import (
    TurnActions,
    TurnResult,
)
from gin_rummy.models import Card, Hand, analyze_hand
from gin_rummy.tracking import TurnRecord, TurnRecorder, TurnSnapshot


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


def play_human_first_discard(game: Game, human_player_idx: int) -> Card:
    """Ask the human for the opening discard (the round runner applies it)."""
    current = game.current_player
    display_game_state(game, human_player_idx, turn_player_name=current.name)
    print("Discard one card to start the game.")
    # Show hand with numbers for selection
    print("\nSelect a card to discard:")
    display_cards = display_hand_by_suit(current.hand, show_numbers=True)
    idx = get_card_choice(game.current_player.hand, "\nCard to discard: ")
    card = display_cards[idx]
    print(f"\nDiscarded {card}")
    return card


def play_human_turn(
    game: Game, human_player_idx: int, tracker: GameTracker | None = None
) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
    """Play a human player's turn.

    Returns:
        (TurnResult, TurnActions, RoundResult), like execute_ai_turn: the
        actions are None when the deck ran out, and the RoundResult is only
        set when the round ended this turn (knock or draw).
    """
    current = game.current_player
    clear_screen()
    display_game_state(game, human_player_idx, turn_player_name=current.name)

    # Capture state before turn (for database tracking)
    snapshot = TurnSnapshot.of(current)
    recorder = TurnRecorder(tracker)
    deadwood_before = current.hand.deadwood_total

    # Drawing phase
    print("\nDraw from:")
    print("  [1] Deck")
    if game.top_of_discard:
        print(f"  [2] Discard pile ({game.top_of_discard})")

    drew_from = "deck"
    card = None

    while True:
        choice = input("\nYour choice: ").strip().lower()
        if choice == "q":
            print("Thanks for playing!")
            sys.exit(0)

        if choice == "a":
            new_state = toggle_assist_values()
            print(f"\nAssist card values: {'ON' if new_state else 'OFF'}")
            clear_screen()
            display_game_state(game, human_player_idx, turn_player_name=current.name)
            print("\nDraw from:")
            print("  [1] Deck")
            if game.top_of_discard:
                print(f"  [2] Discard pile ({game.top_of_discard})")
            continue

        if choice == "1":
            try:
                card = game.draw_from_deck()
                drew_from = "deck"
                print(f"\nDrew {card} from deck")
                break
            except InvalidActionError as e:
                print(f"\n{e}")
                return TurnResult.DRAW, None, game.get_draw_result()
        elif choice == "2" and game.top_of_discard:
            card = game.draw_from_discard()
            drew_from = "discard"
            print(f"\nPicked up {card} from discard")
            break
        else:
            print("Invalid choice")

    # Update display after drawing - show cards for discard selection
    print("\nYour hand:")
    display_cards = display_hand_by_suit(current.hand, show_numbers=True)

    # Discard phase - select card first, then optionally knock
    while True:
        choice = input("\nCard # to discard: ").strip().lower()

        if choice == "q":
            print("Thanks for playing!")
            sys.exit(0)

        if choice == "a":
            new_state = toggle_assist_values()
            print(f"\nAssist card values: {'ON' if new_state else 'OFF'}")
            continue

        # Try to parse as card number
        try:
            idx = int(choice)
            if 1 <= idx <= len(display_cards):
                discard_card = display_cards[idx - 1]

                # Rule: cannot discard the card just taken from the discard pile
                if discard_card == game.discard_blocked_card:
                    print(
                        f"\n❌ Cannot discard {discard_card} - you just took it "
                        f"from the discard pile. Choose a different card."
                    )
                    continue

                # Check if discarding from a meld (potential mistake)
                current_analysis = current.hand.analyze()
                is_in_meld = any(discard_card in meld.cards for meld in current_analysis.melds)

                if is_in_meld:
                    confirm = input(f"\n⚠️  {discard_card} is part of a meld. Discard anyway? (y/n): ").strip().lower()
                    if confirm != "y":
                        print("Choose a different card.")
                        continue

                # Calculate deadwood AFTER discarding this card
                remaining_cards = [c for c in current.hand if c != discard_card]
                post_discard_analysis = analyze_hand(remaining_cards)
                post_discard_deadwood = post_discard_analysis.deadwood_value

                # Check if can knock with the 10-card hand
                can_knock_after = post_discard_deadwood <= game.knock_threshold

                if can_knock_after:
                    print(f"\nDiscarding {discard_card} leaves you with {post_discard_deadwood} deadwood.")
                    knock_choice = input("Knock? (y/n): ").strip().lower()

                    if knock_choice == "y":
                        # Discard and knock (handles pile/history bookkeeping)
                        result = game.knock_with_discard(discard_card)
                        recorder.write(
                            TurnRecord.human(current, snapshot, drew_from, card, discard_card, did_knock=True)
                        )

                        display_round_result(game, result)
                        actions = TurnActions(
                            draw_source=DrawChoice.DISCARD if drew_from == "discard" else DrawChoice.DECK,
                            drawn_card=card,
                            discarded_card=discard_card,
                            did_knock=True,
                            deadwood_before=deadwood_before,
                            deadwood_after=post_discard_deadwood,
                        )
                        return TurnResult.KNOCKED, actions, result

                # Just discard (no knock or declined knock)
                game.discard(discard_card)
                print(f"\nDiscarded {discard_card}")
                recorder.write(TurnRecord.human(current, snapshot, drew_from, card, discard_card, did_knock=False))

                actions = TurnActions(
                    draw_source=DrawChoice.DISCARD if drew_from == "discard" else DrawChoice.DECK,
                    drawn_card=card,
                    discarded_card=discard_card,
                    did_knock=False,
                    deadwood_before=deadwood_before,
                    deadwood_after=current.hand.deadwood_total,
                )
                return TurnResult.CONTINUE, actions, None
            print(f"Please enter a number between 1 and {len(display_cards)}")
        except ValueError:
            print("Please enter a valid card number")
