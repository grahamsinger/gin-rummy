"""Gin Rummy network client.

Connects to a server and plays the game.
"""

from __future__ import annotations

import argparse
import socket
import sys
from typing import Any

from gin_rummy.card import Card, Suit
from gin_rummy.melds import analyze_hand
from gin_rummy.network.protocol import (
    Message,
    MessageType,
    card_to_str,
    discard_msg,
    draw_msg,
    first_discard_msg,
    join_msg,
    knock_msg,
    ready_msg,
    recv_message,
    send_message,
    str_to_card,
)


# ANSI color codes
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Unicode superscript digits
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def superscript(n: int) -> str:
    """Convert a number to Unicode superscript characters."""
    return "".join(SUPERSCRIPTS[int(d)] for d in str(n))


def colored_card(card: Card) -> str:
    """Return card string with color for red suits."""
    s = str(card)
    if card.suit.is_red:
        return f"{RED}{s}{RESET}"
    return s


def clear_screen() -> None:
    """Clear the terminal screen."""
    import os
    os.system("cls" if os.name == "nt" else "clear")


class GinRummyClient:
    """Network client for Gin Rummy."""

    def __init__(self, host: str, port: int = 5555) -> None:
        self.host = host
        self.port = port
        self.socket: socket.socket | None = None
        self.player_name = ""
        self.player_idx = -1
        self.opponent_name = ""
        self.current_state: dict[str, Any] = {}
        self.running = False

    def connect(self, player_name: str) -> bool:
        """Connect to the server and join the game."""
        self.player_name = player_name

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print(f"Connected to {self.host}:{self.port}")
        except ConnectionRefusedError:
            print(f"Error: Could not connect to {self.host}:{self.port}")
            return False
        except socket.gaierror:
            print(f"Error: Could not resolve host {self.host}")
            return False

        # Wait for WELCOME
        msg = recv_message(self.socket)
        if msg.type == MessageType.ERROR:
            print(f"Server error: {msg.payload.get('message', 'Unknown error')}")
            return False

        if msg.type != MessageType.WELCOME:
            print(f"Unexpected message: {msg.type}")
            return False

        # Send JOIN
        send_message(self.socket, join_msg(player_name))
        return True

    def run(self) -> None:
        """Main client loop."""
        if not self.socket:
            return

        self.running = True
        try:
            while self.running:
                msg = recv_message(self.socket)
                self._handle_message(msg)
        except ConnectionError:
            print("\nConnection lost.")
        except KeyboardInterrupt:
            print("\nDisconnecting...")
        finally:
            if self.socket:
                self.socket.close()

    def _handle_message(self, msg: Message) -> None:
        """Process a message from the server."""
        if msg.type == MessageType.WAITING:
            print("Waiting for opponent to connect...")

        elif msg.type == MessageType.GAME_START:
            self.opponent_name = msg.payload.get("opponent_name", "Opponent")
            self.player_idx = msg.payload.get("you_are_player", 0)
            print(f"\nGame starting! You are playing against {self.opponent_name}")
            print()

        elif msg.type == MessageType.STATE:
            self.current_state = msg.payload
            self._display_state()

        elif msg.type == MessageType.YOUR_TURN:
            phase = msg.payload.get("phase", "")
            can_knock = msg.payload.get("can_knock", False)
            self._handle_turn(phase, can_knock)

        elif msg.type == MessageType.OPPONENT_TURN:
            print(f"\n{self.opponent_name}'s turn...")

        elif msg.type == MessageType.DRAW_RESULT:
            card_str = msg.payload.get("card", "")
            source = msg.payload.get("source", "deck")
            card = str_to_card(card_str)
            print(f"You drew {colored_card(card)} from the {source}")

        elif msg.type == MessageType.OPPONENT_DREW:
            source = msg.payload.get("source", "deck")
            if source == "discard":
                card_str = msg.payload.get("card", "")
                card = str_to_card(card_str)
                print(f"{self.opponent_name} picked up {colored_card(card)} from the discard pile")
            else:
                print(f"{self.opponent_name} drew from the deck")

        elif msg.type == MessageType.DISCARD_RESULT:
            pass  # We already know what we discarded

        elif msg.type == MessageType.OPPONENT_DISCARDED:
            card_str = msg.payload.get("card", "")
            card = str_to_card(card_str)
            print(f"{self.opponent_name} discarded {colored_card(card)}")

        elif msg.type == MessageType.ROUND_OVER:
            self._display_round_result(msg.payload)

        elif msg.type == MessageType.GAME_OVER:
            self._display_game_over(msg.payload)
            self.running = False

        elif msg.type == MessageType.ERROR:
            print(f"Error: {msg.payload.get('message', 'Unknown error')}")

        elif msg.type == MessageType.OPPONENT_DISCONNECTED:
            print(f"\n{msg.payload.get('message', 'Opponent disconnected.')}")
            self.running = False

        elif msg.type == MessageType.PONG:
            pass  # Heartbeat response

    def _display_state(self) -> None:
        """Display the current game state."""
        clear_screen()

        state = self.current_state
        your_name = state.get("your_name", self.player_name)
        current_player = state.get("current_player", "")
        dealer = state.get("dealer", "")
        scores = state.get("scores", {})

        print("=" * 60)
        print(f"{'GIN RUMMY':^60}")
        print("=" * 60)
        print()

        # Scores
        score_str = " | ".join(f"{name}: {score}" for name, score in scores.items())
        print(f"Scores: {score_str}")
        print(f"Dealer: {dealer}")
        print()

        # Opponent info
        opponent_count = state.get("opponent_card_count", 10)
        print(f"{self.opponent_name}: {opponent_count} cards")

        # Deck and discard
        deck_count = state.get("deck_count", 0)
        discard_top = state.get("discard_top")
        print(f"Deck: {deck_count} cards")
        if discard_top:
            top_card = str_to_card(discard_top)
            print(f"Discard pile: {colored_card(top_card)}")
        else:
            print("Discard pile: (empty)")
        print()

        # Your hand
        print(f"{your_name}'s hand:")
        hand_strs = state.get("your_hand", [])
        cards = [str_to_card(s) for s in hand_strs]
        self._display_hand(cards)
        print()

    def _display_hand(self, cards: list[Card]) -> None:
        """Display a hand organized by suit with melds bracketed."""
        # Find optimal melds
        analysis = analyze_hand(cards)
        melded_cards: set[Card] = set()
        for meld in analysis.melds:
            melded_cards.update(meld.cards)

        # Group by suit
        cards_by_suit: dict[Suit, list[Card]] = {suit: [] for suit in Suit}
        for card in cards:
            cards_by_suit[card.suit].append(card)

        # Sort each suit by rank
        for suit in cards_by_suit:
            cards_by_suit[suit].sort(key=lambda c: c.rank.value)

        # Build selection order
        suit_order = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
        self._selection_order: list[Card] = []
        for suit in suit_order:
            self._selection_order.extend(cards_by_suit[suit])

        card_to_num: dict[Card, int] = {card: i + 1 for i, card in enumerate(self._selection_order)}

        # Display each suit row
        for suit in suit_order:
            suit_cards = cards_by_suit[suit]
            if not suit_cards:
                continue

            row = f"  {suit.symbol}: "

            # Find consecutive meld groups
            i = 0
            while i < len(suit_cards):
                card = suit_cards[i]
                if card in melded_cards:
                    # Start of a meld group - find its end
                    group = [card]
                    j = i + 1
                    while j < len(suit_cards) and suit_cards[j] in melded_cards:
                        # Check if consecutive rank
                        if suit_cards[j].rank.value == suit_cards[j-1].rank.value + 1:
                            group.append(suit_cards[j])
                            j += 1
                        else:
                            break

                    if len(group) >= 3:
                        # Display as bracketed group
                        row += "["
                        row += " ".join(f"{colored_card(c)}{superscript(card_to_num[c])}" for c in group)
                        row += "] "
                        i = j
                    else:
                        # Not enough for a run, display individually
                        row += f"{colored_card(card)}{superscript(card_to_num[card])} "
                        i += 1
                else:
                    row += f"{colored_card(card)}{superscript(card_to_num[card])} "
                    i += 1

            print(row.rstrip())

        # Calculate and show deadwood
        deadwood = sum(c.deadwood_value for c in cards if c not in melded_cards)
        print(f"\n  Deadwood: {deadwood}")

    def _handle_turn(self, phase: str, can_knock: bool) -> None:
        """Handle player's turn based on phase."""
        if not self.socket:
            return

        if phase == "FIRST_DISCARD":
            self._handle_first_discard()
        elif phase == "DRAWING":
            self._handle_draw_phase()
        elif phase == "DISCARDING":
            self._handle_discard_phase(can_knock)

    def _handle_first_discard(self) -> None:
        """Handle the opening discard from 11 cards."""
        print("\n>>> Your turn: Opening discard (you have 11 cards) <<<")
        card = self._get_discard_choice(can_knock=False)
        if card and self.socket:
            send_message(self.socket, first_discard_msg(card))

    def _handle_draw_phase(self) -> None:
        """Handle the draw phase."""
        print("\n>>> Your turn: Draw a card <<<")
        print("Draw from:")
        print("  [1] Deck")

        discard_top = self.current_state.get("discard_top")
        if discard_top:
            top_card = str_to_card(discard_top)
            print(f"  [2] Discard pile ({colored_card(top_card)})")

        while True:
            choice = input("\nYour choice (1/2): ").strip()
            if choice == "1":
                if self.socket:
                    send_message(self.socket, draw_msg("deck"))
                break
            elif choice == "2" and discard_top:
                if self.socket:
                    send_message(self.socket, draw_msg("discard"))
                break
            elif choice.lower() == "q":
                self.running = False
                return
            else:
                print("Invalid choice. Enter 1 or 2.")

    def _handle_discard_phase(self, can_knock: bool) -> None:
        """Handle the discard phase."""
        print("\n>>> Your turn: Discard a card <<<")
        if can_knock:
            print("(You can knock with 'k')")

        card = self._get_discard_choice(can_knock)
        if not card or not self.socket:
            return

        # Check if player chose to knock
        if can_knock and hasattr(self, "_wants_to_knock") and self._wants_to_knock:
            send_message(self.socket, knock_msg(card))
            self._wants_to_knock = False
        else:
            send_message(self.socket, discard_msg(card))

    def _get_discard_choice(self, can_knock: bool) -> Card | None:
        """Get card choice for discard."""
        hand_strs = self.current_state.get("your_hand", [])
        cards = [str_to_card(s) for s in hand_strs]

        if not hasattr(self, "_selection_order") or len(self._selection_order) != len(cards):
            # Rebuild selection order if needed
            self._selection_order = cards

        while True:
            prompt = f"Enter card number (1-{len(cards)})"
            if can_knock:
                prompt += " or 'k' to knock"
            prompt += ": "

            choice = input(prompt).strip().lower()

            if choice == "q":
                self.running = False
                return None

            if choice == "k" and can_knock:
                self._wants_to_knock = True
                # Still need to choose a card to discard
                print("Choose card to discard with your knock:")
                continue

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(self._selection_order):
                    return self._selection_order[idx]
                else:
                    print(f"Enter a number between 1 and {len(cards)}")
            except ValueError:
                print("Invalid input. Enter a number or 'k' to knock.")

    def _display_round_result(self, payload: dict[str, Any]) -> None:
        """Display the round result."""
        print("\n" + "=" * 60)
        print(f"{'ROUND OVER':^60}")
        print("=" * 60)

        is_draw = payload.get("is_draw", False)
        is_gin = payload.get("is_gin", False)
        is_undercut = payload.get("is_undercut", False)
        winner = payload.get("winner")
        points = payload.get("points", 0)
        scores = payload.get("scores", {})
        hands = payload.get("hands", {})

        if is_draw:
            print("\nThe round ended in a DRAW (deck exhausted).")
        else:
            if is_gin:
                print(f"\n{winner} wins with GIN!")
            elif is_undercut:
                print(f"\n{winner} wins with an UNDERCUT!")
            else:
                print(f"\n{winner} wins the round!")
            print(f"Points awarded: {points}")

        # Show both hands
        print("\nFinal hands:")
        for name, hand_strs in hands.items():
            cards = [str_to_card(s) for s in hand_strs]
            deadwood = self._calculate_deadwood(cards)
            cards_display = " ".join(colored_card(c) for c in sorted(cards))
            print(f"  {name} (deadwood {deadwood}): {cards_display}")

        print(f"\nScores: {' | '.join(f'{n}: {s}' for n, s in scores.items())}")

        # Wait for player to continue
        input("\nPress Enter to continue to next round...")
        if self.socket:
            send_message(self.socket, ready_msg())

    def _calculate_deadwood(self, cards: list[Card]) -> int:
        """Calculate deadwood value for a list of cards."""
        analysis = analyze_hand(cards)
        return analysis.deadwood_value

    def _display_game_over(self, payload: dict[str, Any]) -> None:
        """Display game over message."""
        print("\n" + "=" * 60)
        print(f"{'GAME OVER':^60}")
        print("=" * 60)

        winner = payload.get("winner", "Unknown")
        final_scores = payload.get("final_scores", {})

        print(f"\n{BOLD}{winner} WINS THE GAME!{RESET}")
        print(f"\nFinal scores: {' | '.join(f'{n}: {s}' for n, s in final_scores.items())}")
        print()


def main() -> None:
    """Entry point for gin-client command."""
    parser = argparse.ArgumentParser(description="Gin Rummy Network Client")
    parser.add_argument("host", nargs="?", help="Server IP address or hostname")
    parser.add_argument("--port", "-p", type=int, default=5555, help="Server port")
    parser.add_argument("--name", "-n", help="Your player name")

    args = parser.parse_args()

    # Get host if not provided
    host = args.host
    if not host:
        host = input("Enter server IP address: ").strip()
        if not host:
            print("Error: Server address required")
            sys.exit(1)

    # Get player name if not provided
    name = args.name
    if not name:
        name = input("Enter your name: ").strip()
        if not name:
            name = "Player"

    client = GinRummyClient(host, args.port)
    if client.connect(name):
        client.run()


if __name__ == "__main__":
    main()
