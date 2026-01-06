"""Terminal interface for Gin Rummy."""

from __future__ import annotations

import os
import sys
import time
from enum import Enum, auto
from pathlib import Path

from gin_rummy.ai import BasicAI, DrawChoice, ContextAwareAI
from gin_rummy.models import Card, Suit, Rank, Hand, MeldType, HandAnalysis, Player, analyze_hand
from gin_rummy.config import get_config, load_config
from gin_rummy.database import GameTracker, card_to_db_str, cards_to_db_list
from gin_rummy.game import Game, GamePhase, InvalidActionError
from gin_rummy.game_runner import (
    TurnResult,
    TurnActions,
    TurnCallbacks,
    execute_ai_turn,
)


# ANSI color codes for terminal output
RED = "\033[91m"      # Bright red for hearts/diamonds
RESET = "\033[0m"     # Reset to default

# Unicode superscript digits for card selection numbers
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def superscript(n: int) -> str:
    """Convert a number to Unicode superscript characters."""
    return "".join(SUPERSCRIPTS[int(d)] for d in str(n))


def clear_screen() -> None:
    """Clear the terminal screen if enabled in config."""
    if get_config().display.clear_screen:
        os.system("cls" if os.name == "nt" else "clear")


# Runtime state for assist mode toggle (overrides config)
_assist_show_values: bool | None = None


def toggle_assist_values() -> bool:
    """Toggle assist mode value display. Returns new state."""
    global _assist_show_values
    config = get_config()
    if _assist_show_values is None:
        _assist_show_values = not config.assist.show_values
    else:
        _assist_show_values = not _assist_show_values
    return _assist_show_values


def get_assist_show_values() -> bool:
    """Get current assist show_values state (runtime override or config)."""
    if _assist_show_values is not None:
        return _assist_show_values
    return get_config().assist.show_values


def display_assist_info(game: Game, human_player_idx: int) -> None:
    """Display assist information (opponent known cards and buried discards).

    Args:
        game: The game instance.
        human_player_idx: Index of the human player (0 or 1).
    """
    config = get_config()
    if not config.assist.enabled:
        return

    show_values = get_assist_show_values()
    context = game.get_game_context(human_player_idx)

    print("--- Assist ---")

    # Opponent's known cards (pickups minus re-discards)
    if context.known_cards:
        opponent_known = context.known_cards.opponent_hand_known
        if show_values and opponent_known:
            cards_str = ", ".join(str(c) for c in sorted(opponent_known, key=lambda c: (c.suit.value, c.rank.value)))
            print(f"Opponent has: {cards_str}")
        else:
            count = len(opponent_known)
            print(f"Opponent has: {count} known card{'s' if count != 1 else ''}")

        # Dead cards (buried discards - cards in discard pile that can't be drawn)
        dead = context.dead_cards
        if show_values and dead:
            cards_str = ", ".join(str(c) for c in sorted(dead, key=lambda c: (c.suit.value, c.rank.value)))
            print(f"Dead cards: {cards_str}")
        else:
            print(f"Dead cards: {len(dead)}")
    else:
        # Fallback if known_cards not available
        print(f"Dead cards: {len(context.discard_history)}")

    print("(Press 'a' to toggle card values)")


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


def display_hand_by_suit(hand: Hand, show_numbers: bool = True) -> list[Card]:
    """Display a hand grouped by suit with melds in brackets.

    Cards are positioned by rank (A-K) so runs are visually aligned.
    Melded cards are wrapped in brackets. Red suits are colored.

    Args:
        hand: The hand to display.
        show_numbers: If True, show superscript selection numbers.

    Returns:
        List of cards in selection order (for mapping numbers to cards).
    """
    analysis = hand.analyze()

    # Build set of melded cards for quick lookup
    melded_cards: set[Card] = set()
    for meld in analysis.melds:
        melded_cards.update(meld.cards)

    # Group cards by suit
    cards_by_suit: dict[Suit, list[Card]] = {suit: [] for suit in Suit}
    for card in hand:
        cards_by_suit[card.suit].append(card)

    # Sort each suit by rank
    for suit in cards_by_suit:
        cards_by_suit[suit].sort(key=lambda c: c.rank.value)

    # Build selection order list (spades, hearts, diamonds, clubs - by rank within each)
    suit_order = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
    selection_order: list[Card] = []
    for suit in suit_order:
        selection_order.extend(cards_by_suit[suit])

    # Create card to selection number mapping
    card_to_num: dict[Card, int] = {card: i + 1 for i, card in enumerate(selection_order)}

    # Column width for each rank position (A, 2, 3, ..., K)
    # Reduced for more compact display
    col_width = 3

    # Display each suit row
    for suit in suit_order:
        suit_cards = cards_by_suit[suit]
        if not suit_cards:
            continue

        # Build the row string with cards at their rank positions
        # Track which positions have cards and which are in melds
        row_parts: list[str] = []
        row_parts.append(f"{suit.symbol}: ")

        # Find meld groups (consecutive melded cards)
        meld_groups: list[list[Card]] = []
        current_group: list[Card] = []
        for card in suit_cards:
            if card in melded_cards:
                current_group.append(card)
            else:
                if current_group:
                    meld_groups.append(current_group)
                    current_group = []
        if current_group:
            meld_groups.append(current_group)

        # Build positions array (13 positions for A-K)
        positions: list[str] = [""] * 13
        in_meld_group: list[bool] = [False] * 13

        for card in suit_cards:
            pos = card.rank.value - 1  # 0-indexed
            num_str = superscript(card_to_num[card]) if show_numbers else ""
            card_str = card.colored_str(RED, RESET) + num_str
            positions[pos] = card_str
            in_meld_group[pos] = card in melded_cards

        # Build row with brackets around meld groups
        row = f"{suit.symbol}: "
        i = 0
        while i < 13:
            if positions[i]:
                # Check if this starts a meld group
                if in_meld_group[i]:
                    # Find end of meld group
                    group_start = i
                    while i < 13 and in_meld_group[i] and positions[i]:
                        i += 1
                    group_end = i

                    # Add opening bracket
                    row += "["
                    for j in range(group_start, group_end):
                        row += positions[j]
                        if j < group_end - 1:
                            row += " "
                    row += "] "
                else:
                    row += positions[i] + " "
                    i += 1
            else:
                # Empty position - add spacing based on rank
                row += " " * col_width
                i += 1

        print(f"  {row.rstrip()}")

    # Print deadwood total
    print(f"\n  Deadwood: {analysis.deadwood_value}")

    return selection_order


def display_game_state(
    game: Game,
    human_player_idx: int,
    show_opponent: bool = False,
    turn_player_name: str | None = None
) -> None:
    """Display the current game state from human player's perspective.

    Args:
        game: The game instance.
        human_player_idx: Index of the human player (0 or 1).
        show_opponent: If True, show opponent's cards (for debugging).
        turn_player_name: If provided, show whose turn it is at the top.
    """
    human = game.players[human_player_idx]
    opponent = game.players[1 - human_player_idx]

    print("\n" + "=" * 50)
    print("              GIN RUMMY")
    print("=" * 50)

    # Turn indicator
    if turn_player_name:
        print(f"\n>>> {turn_player_name}'s turn <<<")

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

    # Assist mode info
    display_assist_info(game, human_player_idx)

    # Human player's hand with meld analysis
    print(f"\n{human.name}'s hand:")
    display_hand_by_suit(human.hand, show_numbers=False)

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
    current = game.current_player
    display_game_state(game, human_player_idx, turn_player_name=current.name)
    print(f"Discard one card to start the game.")
    # Show hand with numbers for selection
    print(f"\nSelect a card to discard:")
    display_cards = display_hand_by_suit(current.hand, show_numbers=True)
    idx = get_card_choice(game.current_player.hand, "\nCard to discard: ")
    card = display_cards[idx]
    game.discard_to_start(card)
    print(f"\nDiscarded {card}")


def play_ai_first_discard(game: Game, ai: BasicAI) -> None:
    """Handle AI's opening discard."""
    delay = get_config().display.ai_turn_delay
    ai_name = game.current_player.name
    print(f"\n{ai_name} is choosing a card to discard...")
    time.sleep(delay * 2)  # Slightly longer for first discard

    discard = ai.decide_discard(game.current_player.hand)
    game.discard_to_start(discard)
    print(f"{ai_name} discarded {discard}")
    time.sleep(delay)


def play_human_turn(
    game: Game,
    human_player_idx: int,
    tracker: GameTracker | None = None
) -> TurnResult:
    """Play a human player's turn.

    Returns:
        TurnResult indicating whether round continues, ended by knock, or draw.
    """
    current = game.current_player
    clear_screen()
    display_game_state(game, human_player_idx, turn_player_name=current.name)

    # Capture state before turn (for database tracking)
    cards_before = cards_to_db_list(list(current.hand))
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
                return TurnResult.DRAW
        elif choice == "2" and game.top_of_discard:
            card = game.draw_from_discard()
            drew_from = "discard"
            print(f"\nPicked up {card} from discard")
            break
        else:
            print("Invalid choice")

    # Update display after drawing - show cards for discard selection
    print(f"\nYour hand:")
    display_cards = display_hand_by_suit(current.hand, show_numbers=True)

    # Discard phase - select card first, then optionally knock
    while True:
        choice = input(f"\nCard # to discard: ").strip().lower()

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
                        # Discard the card first, then knock
                        current.hand.remove(discard_card)
                        game.discard_pile.append(discard_card)
                        game._discard_history.append(discard_card)

                        # Record turn before knock
                        if tracker and card:
                            cards_after = cards_to_db_list(list(current.hand))
                            tracker.record_turn(
                                player_name=current.name,
                                drew_from=drew_from,
                                card_drawn=card_to_db_str(card),
                                card_discarded=card_to_db_str(discard_card),
                                did_knock=True,
                                cards_before=cards_before,
                                cards_after=cards_after,
                                deadwood_before=deadwood_before,
                                deadwood_after=post_discard_deadwood
                            )

                        result = game.knock()
                        display_round_result(game)
                        return TurnResult.KNOCKED

                # Just discard (no knock or declined knock)
                game.discard(discard_card)
                print(f"\nDiscarded {discard_card}")

                # Record turn
                if tracker and card:
                    cards_after = cards_to_db_list(list(current.hand))
                    deadwood_after = current.hand.deadwood_total
                    tracker.record_turn(
                        player_name=current.name,
                        drew_from=drew_from,
                        card_drawn=card_to_db_str(card),
                        card_discarded=card_to_db_str(discard_card),
                        did_knock=False,
                        cards_before=cards_before,
                        cards_after=cards_after,
                        deadwood_before=deadwood_before,
                        deadwood_after=deadwood_after
                    )

                return TurnResult.CONTINUE
            print(f"Please enter a number between 1 and {len(display_cards)}")
        except ValueError:
            print("Please enter a valid card number")


class CLITurnCallbacks:
    """Callbacks for AI turn side effects in CLI mode.

    Handles UI output (print statements, delays) and database tracking.
    """

    def __init__(
        self,
        game: Game,
        tracker: GameTracker | None,
        delay: float,
        cards_before: list[str],
    ) -> None:
        self.game = game
        self.tracker = tracker
        self.delay = delay
        self.cards_before = cards_before
        self.config = get_config()

    def on_draw(self, player: Player, source: DrawChoice, card: Card) -> None:
        """Print draw message and add delay."""
        if source == DrawChoice.DISCARD:
            print(f"{player.name} picked up {card} from discard pile")
        else:
            print(f"{player.name} drew from deck")
        time.sleep(self.delay)

    def on_discard(self, player: Player, card: Card) -> None:
        """Print discard message and add delay."""
        print(f"{player.name} discarded {card}")
        time.sleep(self.delay)

    def on_knock(self, player: Player, discard: Card, deadwood: int) -> None:
        """Print knock message, display round result, and add delay."""
        print(f"{player.name} knocks!")
        time.sleep(self.delay)
        display_round_result(self.game)

    def on_turn_complete(self, player: Player, actions: TurnActions) -> None:
        """Record turn to database tracker if enabled."""
        if not self.tracker:
            return

        drew_from = "discard" if actions.draw_source == DrawChoice.DISCARD else "deck"

        # Get cards after turn
        if actions.did_knock:
            cards_after = cards_to_db_list([c for c in player.hand if c != actions.discarded_card])
        else:
            cards_after = cards_to_db_list(list(player.hand))

        turn_id = self.tracker.record_turn(
            player_name=player.name,
            drew_from=drew_from,
            card_drawn=card_to_db_str(actions.drawn_card),
            card_discarded=card_to_db_str(actions.discarded_card),
            did_knock=actions.did_knock,
            cards_before=self.cards_before,
            cards_after=cards_after,
            deadwood_before=actions.deadwood_before,
            deadwood_after=actions.deadwood_after,
        )

        if self.config.database.track_ai_decisions:
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type="draw",
                choice=drew_from,
                reasoning=f"Drew {card_to_db_str(actions.drawn_card)} from {drew_from}",
            )
            if actions.did_knock:
                self.tracker.record_ai_decision(
                    turn_id=turn_id,
                    decision_type="knock",
                    choice="yes",
                    reasoning=f"Knocked with {actions.deadwood_after} deadwood",
                )
            else:
                self.tracker.record_ai_decision(
                    turn_id=turn_id,
                    decision_type="discard",
                    choice=card_to_db_str(actions.discarded_card),
                    reasoning=f"Discarded {card_to_db_str(actions.discarded_card)}, deadwood {actions.deadwood_before} -> {actions.deadwood_after}",
                )


def play_ai_turn(
    game: Game,
    ai: BasicAI,
    human_player_idx: int,
    tracker: GameTracker | None = None,
) -> TurnResult:
    """Play an AI turn using shared game runner logic.

    Args:
        game: Current game state.
        ai: The AI making decisions.
        human_player_idx: Index of human player (unused, kept for API compatibility).
        tracker: Optional database tracker for recording turns.

    Returns:
        TurnResult indicating whether round continues, ended by knock, or draw.
    """
    config = get_config()
    delay = config.display.ai_turn_delay
    current = game.current_player

    # Initial delay before AI acts
    time.sleep(delay)

    # Capture state before turn (needed for database tracking)
    cards_before = cards_to_db_list(list(current.hand))

    # Create callbacks for CLI-specific side effects
    callbacks = CLITurnCallbacks(game, tracker, delay, cards_before)

    # Execute the turn using shared game logic
    result, _, _ = execute_ai_turn(game, ai, callbacks=callbacks)

    return result


def display_round_result(game: Game) -> None:
    """Display the result of a round."""
    print("\n" + "=" * 50)
    print("           ROUND OVER")
    print("=" * 50)

    # Show both hands with melds
    for player in game.players:
        print(f"\n{player.name}'s hand:")
        display_hand_by_suit(player.hand, show_numbers=False)

    print(f"\nScores: {game.players[0].name}: {game.players[0].score}  |  "
          f"{game.players[1].name}: {game.players[1].score}")


def play_round_vs_ai(
    game: Game,
    ai: BasicAI,
    human_player_idx: int,
    tracker: GameTracker | None = None
) -> None:
    """Play a complete round against AI."""
    game.deal()

    # Start hand tracking
    if tracker:
        tracker.start_hand(dealer_name=game.dealer.name)

    # Determine who does first discard (non-dealer)
    non_dealer_idx = 1 - game.dealer_idx

    clear_screen()

    if non_dealer_idx == human_player_idx:
        # Human does first discard
        play_human_first_discard(game, human_player_idx)
    else:
        # AI does first discard
        ai_name = game.current_player.name
        display_game_state(game, human_player_idx, turn_player_name=ai_name)
        play_ai_first_discard(game, ai)

    # Main game loop
    turn_result = TurnResult.CONTINUE
    while game.phase not in (GamePhase.ROUND_OVER, GamePhase.KNOCKED):
        if game.current_player_idx == human_player_idx:
            turn_result = play_human_turn(game, human_player_idx, tracker)
            if turn_result != TurnResult.CONTINUE:
                break
        else:
            clear_screen()
            ai_name = game.current_player.name
            display_game_state(game, human_player_idx, turn_player_name=ai_name)
            turn_result = play_ai_turn(game, ai, human_player_idx, tracker)
            if turn_result != TurnResult.CONTINUE:
                break
            # Continue to human's turn without prompting

    # End hand tracking
    if tracker:
        if turn_result == TurnResult.DRAW:
            tracker.end_hand(
                winner_name=None,
                loser_name=None,
                points=0,
                is_draw=True,
                knocker_name=None,
                winner_deadwood=0,
                loser_deadwood=0
            )
        elif turn_result == TurnResult.KNOCKED:
            # Determine winner from scores (the one who just gained points)
            p0_score_before = game.players[0].score
            p1_score_before = game.players[1].score
            # Winner is whoever has more points now (knock already applied)
            if game.players[0].score > game.players[1].score:
                winner = game.players[0]
                loser = game.players[1]
                points = game.players[0].score - p0_score_before
            else:
                winner = game.players[1]
                loser = game.players[0]
                points = game.players[1].score - p1_score_before
            # Check for gin/undercut based on deadwood
            p0_dw = game.players[0].hand.deadwood_total
            p1_dw = game.players[1].hand.deadwood_total
            is_gin = min(p0_dw, p1_dw) == 0
            # Undercut if defender won
            knocker_idx = 1 - game.current_player_idx  # current switched after knock
            knocker = game.players[knocker_idx]
            is_undercut = winner != knocker
            tracker.end_hand(
                winner_name=winner.name,
                loser_name=loser.name,
                points=points,
                is_gin=is_gin,
                is_undercut=is_undercut,
                is_draw=False,
                knocker_name=knocker.name,
                winner_deadwood=winner.hand.deadwood_total,
                loser_deadwood=loser.hand.deadwood_total
            )

    if turn_result == TurnResult.DRAW:
        print("\nRound ended in a DRAW (deck exhausted)")

    input("\nPress Enter to continue...")


def play_round_pvp(game: Game, tracker: GameTracker | None = None) -> None:
    """Play a complete round player vs player."""
    game.deal()

    # Start hand tracking
    if tracker:
        tracker.start_hand(dealer_name=game.dealer.name)

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
        turn_result = play_human_turn(game, game.current_player_idx, tracker)
        if turn_result != TurnResult.CONTINUE:
            break
        if game.phase not in (GamePhase.ROUND_OVER, GamePhase.KNOCKED):
            input("\nPress Enter for next player's turn...")

    # End hand tracking
    if tracker:
        if turn_result == TurnResult.DRAW:
            tracker.end_hand(
                winner_name=None,
                loser_name=None,
                points=0,
                is_draw=True,
                knocker_name=None,
                winner_deadwood=0,
                loser_deadwood=0
            )
        elif turn_result == TurnResult.KNOCKED:
            if game.players[0].score > game.players[1].score:
                winner = game.players[0]
                loser = game.players[1]
            else:
                winner = game.players[1]
                loser = game.players[0]
            p0_dw = game.players[0].hand.deadwood_total
            p1_dw = game.players[1].hand.deadwood_total
            is_gin = min(p0_dw, p1_dw) == 0
            knocker_idx = 1 - game.current_player_idx
            knocker = game.players[knocker_idx]
            is_undercut = winner != knocker
            # Calculate points from difference
            points = abs(p0_dw - p1_dw)
            if is_gin or is_undercut:
                points += 25
            tracker.end_hand(
                winner_name=winner.name,
                loser_name=loser.name,
                points=points,
                is_gin=is_gin,
                is_undercut=is_undercut,
                is_draw=False,
                knocker_name=knocker.name,
                winner_deadwood=winner.hand.deadwood_total,
                loser_deadwood=loser.hand.deadwood_total
            )

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
        tracker.end_game(
            winner_name=winner_name,
            score_p1=game.players[0].score,
            score_p2=game.players[1].score
        )

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
