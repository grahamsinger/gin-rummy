"""Gin Rummy network server.

Manages game state and handles two client connections.
"""

from __future__ import annotations

import argparse
import selectors
import socket
import sys
from dataclasses import dataclass, field
from typing import Any

from gin_rummy.card import Card
from gin_rummy.game import Game, GamePhase, InvalidActionError, RoundResult
from gin_rummy.network.protocol import (
    Message,
    MessageType,
    card_to_str,
    cards_to_str_list,
    error_msg,
    recv_message,
    send_message,
    str_to_card,
)


@dataclass
class ClientConnection:
    """Represents a connected client."""

    socket: socket.socket
    player_name: str = ""
    player_idx: int = -1  # 0 or 1 once assigned


@dataclass
class GameSession:
    """Manages a game between two connected players."""

    clients: list[ClientConnection] = field(default_factory=list)
    game: Game | None = None
    player_names: list[str] = field(default_factory=list)

    @property
    def is_full(self) -> bool:
        """Return True if two players are connected."""
        return len(self.clients) == 2

    def add_client(self, client: ClientConnection) -> int:
        """Add a client and return their player index."""
        idx = len(self.clients)
        client.player_idx = idx
        self.clients.append(client)
        self.player_names.append(client.player_name)
        return idx

    def get_opponent(self, player_idx: int) -> ClientConnection:
        """Get the opponent's connection."""
        return self.clients[1 - player_idx]

    def start_game(self) -> None:
        """Initialize the game with both players."""
        self.game = Game(self.player_names[0], self.player_names[1])
        self.game.deal()

    def build_state_for_player(self, player_idx: int) -> dict[str, Any]:
        """Build game state dict for a specific player (hides opponent hand)."""
        if not self.game:
            return {}

        player = self.game.players[player_idx]
        opponent = self.game.players[1 - player_idx]

        return {
            "phase": self.game.phase.name,
            "your_hand": cards_to_str_list(sorted(player.hand)),
            "opponent_card_count": len(opponent.hand),
            "discard_top": card_to_str(self.game.top_of_discard) if self.game.top_of_discard else None,
            "deck_count": len(self.game.deck),
            "scores": {
                self.player_names[0]: self.game.players[0].score,
                self.player_names[1]: self.game.players[1].score,
            },
            "current_player": self.game.current_player.name,
            "can_knock": self.game.can_knock if self.game.current_player_idx == player_idx else False,
            "dealer": self.game.dealer.name,
            "your_name": player.name,
        }


class GinRummyServer:
    """Network server for Gin Rummy multiplayer."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5555) -> None:
        self.host = host
        self.port = port
        self.selector = selectors.DefaultSelector()
        self.session = GameSession()
        self.server_socket: socket.socket | None = None
        self.running = False

    def start(self) -> None:
        """Start the server and listen for connections."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(2)
        self.server_socket.setblocking(False)

        self.selector.register(self.server_socket, selectors.EVENT_READ, data=None)

        # Get actual IP for display
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except socket.gaierror:
            local_ip = "127.0.0.1"

        print(f"Gin Rummy Server started")
        print(f"Listening on {local_ip}:{self.port}")
        print("Waiting for 2 players to connect...")
        print()

        self.running = True
        self._run_loop()

    def _run_loop(self) -> None:
        """Main event loop."""
        try:
            while self.running:
                events = self.selector.select(timeout=1.0)
                for key, mask in events:
                    if key.data is None:
                        # Server socket - accept new connection
                        self._accept_connection()
                    else:
                        # Client socket - handle message
                        self._handle_client(key.data)
        except KeyboardInterrupt:
            print("\nServer shutting down...")
        finally:
            self._cleanup()

    def _accept_connection(self) -> None:
        """Accept a new client connection."""
        if not self.server_socket:
            return

        conn, addr = self.server_socket.accept()
        print(f"Connection from {addr}")

        if self.session.is_full:
            # Already have 2 players, reject
            try:
                send_message(conn, error_msg("Game is full"))
            except Exception:
                pass
            conn.close()
            return

        conn.setblocking(False)
        client = ClientConnection(socket=conn)
        self.selector.register(conn, selectors.EVENT_READ, data=client)

        # Send welcome, wait for JOIN
        send_message(conn, Message(MessageType.WELCOME, {"message": "Welcome to Gin Rummy!"}))

    def _handle_client(self, client: ClientConnection) -> None:
        """Handle incoming message from a client."""
        try:
            msg = recv_message(client.socket)
        except ConnectionError:
            self._handle_disconnect(client)
            return
        except Exception as e:
            print(f"Error receiving from {client.player_name or 'unknown'}: {e}")
            self._handle_disconnect(client)
            return

        self._process_message(client, msg)

    def _process_message(self, client: ClientConnection, msg: Message) -> None:
        """Process a message from a client."""
        if msg.type == MessageType.JOIN:
            self._handle_join(client, msg)
        elif msg.type == MessageType.DRAW:
            self._handle_draw(client, msg)
        elif msg.type == MessageType.DISCARD:
            self._handle_discard(client, msg)
        elif msg.type == MessageType.KNOCK:
            self._handle_knock(client, msg)
        elif msg.type == MessageType.FIRST_DISCARD:
            self._handle_first_discard(client, msg)
        elif msg.type == MessageType.READY:
            self._handle_ready(client, msg)
        elif msg.type == MessageType.PING:
            send_message(client.socket, Message(MessageType.PONG))
        elif msg.type == MessageType.QUIT:
            self._handle_disconnect(client)
        else:
            send_message(client.socket, error_msg(f"Unknown message type: {msg.type}"))

    def _handle_join(self, client: ClientConnection, msg: Message) -> None:
        """Handle JOIN message from a client."""
        player_name = msg.payload.get("player_name", f"Player{len(self.session.clients) + 1}")
        client.player_name = player_name

        idx = self.session.add_client(client)
        print(f"Player {idx + 1} joined: {player_name}")

        if not self.session.is_full:
            # Wait for second player
            send_message(client.socket, Message(MessageType.WAITING, {
                "message": "Waiting for opponent to connect..."
            }))
        else:
            # Both players connected - start game
            self._start_game()

    def _start_game(self) -> None:
        """Start the game with both players."""
        self.session.start_game()

        # Notify both players
        for client in self.session.clients:
            opponent = self.session.get_opponent(client.player_idx)
            send_message(client.socket, Message(MessageType.GAME_START, {
                "opponent_name": opponent.player_name,
                "you_are_player": client.player_idx,
            }))

        # Send initial state and turn notifications
        self._broadcast_state()
        self._notify_turns()

    def _broadcast_state(self) -> None:
        """Send current game state to both players."""
        for client in self.session.clients:
            state = self.session.build_state_for_player(client.player_idx)
            send_message(client.socket, Message(MessageType.STATE, state))

    def _notify_turns(self) -> None:
        """Notify players whose turn it is."""
        game = self.session.game
        if not game:
            return

        for client in self.session.clients:
            if client.player_idx == game.current_player_idx:
                send_message(client.socket, Message(MessageType.YOUR_TURN, {
                    "phase": game.phase.name,
                    "can_knock": game.can_knock,
                }))
            else:
                send_message(client.socket, Message(MessageType.OPPONENT_TURN, {
                    "phase": game.phase.name,
                }))

    def _validate_current_player(self, client: ClientConnection) -> bool:
        """Check if it's this client's turn."""
        game = self.session.game
        if not game:
            send_message(client.socket, error_msg("Game not started"))
            return False
        if client.player_idx != game.current_player_idx:
            send_message(client.socket, error_msg("Not your turn"))
            return False
        return True

    def _handle_draw(self, client: ClientConnection, msg: Message) -> None:
        """Handle DRAW message."""
        if not self._validate_current_player(client):
            return

        game = self.session.game
        if not game or game.phase != GamePhase.DRAWING:
            send_message(client.socket, error_msg("Cannot draw now"))
            return

        source = msg.payload.get("source", "deck")

        try:
            if source == "deck":
                card = game.draw_from_deck()
            elif source == "discard":
                card = game.draw_from_discard()
            else:
                send_message(client.socket, error_msg(f"Invalid draw source: {source}"))
                return
        except InvalidActionError as e:
            # Check if round ended due to empty deck
            if game.phase == GamePhase.ROUND_OVER:
                self._handle_round_end(game.get_draw_result())
                return
            send_message(client.socket, error_msg(str(e)))
            return

        # Send result to drawing player
        send_message(client.socket, Message(MessageType.DRAW_RESULT, {
            "card": card_to_str(card),
            "source": source,
        }))

        # Notify opponent
        opponent = self.session.get_opponent(client.player_idx)
        opponent_payload: dict[str, Any] = {"source": source}
        if source == "discard":
            opponent_payload["card"] = card_to_str(card)  # Opponent sees what was picked up
        send_message(opponent.socket, Message(MessageType.OPPONENT_DREW, opponent_payload))

        self._broadcast_state()
        self._notify_turns()

    def _handle_discard(self, client: ClientConnection, msg: Message) -> None:
        """Handle DISCARD message."""
        if not self._validate_current_player(client):
            return

        game = self.session.game
        if not game or game.phase != GamePhase.DISCARDING:
            send_message(client.socket, error_msg("Cannot discard now"))
            return

        card_str = msg.payload.get("card", "")
        try:
            card = str_to_card(card_str)
        except ValueError as e:
            send_message(client.socket, error_msg(f"Invalid card: {e}"))
            return

        try:
            game.discard(card)
        except InvalidActionError as e:
            send_message(client.socket, error_msg(str(e)))
            return

        # Confirm to player
        send_message(client.socket, Message(MessageType.DISCARD_RESULT, {
            "card": card_to_str(card),
        }))

        # Notify opponent
        opponent = self.session.get_opponent(client.player_idx)
        send_message(opponent.socket, Message(MessageType.OPPONENT_DISCARDED, {
            "card": card_to_str(card),
        }))

        self._broadcast_state()
        self._notify_turns()

    def _handle_knock(self, client: ClientConnection, msg: Message) -> None:
        """Handle KNOCK message (includes final discard)."""
        if not self._validate_current_player(client):
            return

        game = self.session.game
        if not game or game.phase != GamePhase.DISCARDING:
            send_message(client.socket, error_msg("Cannot knock now"))
            return

        # First discard the card
        card_str = msg.payload.get("card", "")
        try:
            card = str_to_card(card_str)
        except ValueError as e:
            send_message(client.socket, error_msg(f"Invalid card: {e}"))
            return

        try:
            game.current_player.hand.remove(card)
            game.discard_pile.append(card)
        except (ValueError, KeyError) as e:
            send_message(client.socket, error_msg(f"Card not in hand: {card_str}"))
            return

        # Now knock
        try:
            result = game.knock()
        except InvalidActionError as e:
            # Undo the discard
            game.discard_pile.pop()
            game.current_player.hand.add(card)
            send_message(client.socket, error_msg(str(e)))
            return

        self._handle_round_end(result)

    def _handle_first_discard(self, client: ClientConnection, msg: Message) -> None:
        """Handle FIRST_DISCARD message (non-dealer's opening discard)."""
        if not self._validate_current_player(client):
            return

        game = self.session.game
        if not game or game.phase != GamePhase.FIRST_DISCARD:
            send_message(client.socket, error_msg("Cannot first-discard now"))
            return

        card_str = msg.payload.get("card", "")
        try:
            card = str_to_card(card_str)
        except ValueError as e:
            send_message(client.socket, error_msg(f"Invalid card: {e}"))
            return

        try:
            game.discard_to_start(card)
        except InvalidActionError as e:
            send_message(client.socket, error_msg(str(e)))
            return

        # Confirm and notify
        send_message(client.socket, Message(MessageType.DISCARD_RESULT, {
            "card": card_to_str(card),
        }))

        opponent = self.session.get_opponent(client.player_idx)
        send_message(opponent.socket, Message(MessageType.OPPONENT_DISCARDED, {
            "card": card_to_str(card),
        }))

        self._broadcast_state()
        self._notify_turns()

    def _handle_round_end(self, result: RoundResult) -> None:
        """Handle end of round."""
        game = self.session.game
        if not game:
            return

        # Build result payload
        payload: dict[str, Any] = {
            "is_draw": result.is_draw,
            "is_gin": result.is_gin,
            "is_undercut": result.is_undercut,
            "points": result.points,
        }

        if result.winner:
            payload["winner"] = result.winner.name
            payload["loser"] = result.loser.name if result.loser else None
        else:
            payload["winner"] = None

        # Include both hands for display
        payload["hands"] = {
            self.session.player_names[0]: cards_to_str_list(sorted(game.players[0].hand)),
            self.session.player_names[1]: cards_to_str_list(sorted(game.players[1].hand)),
        }

        payload["scores"] = {
            self.session.player_names[0]: game.players[0].score,
            self.session.player_names[1]: game.players[1].score,
        }

        # Check for game over (target score reached)
        from gin_rummy.config import get_config
        config = get_config()
        target = config.game_rules.target_score

        game_over = False
        final_winner = None
        for player in game.players:
            if player.score >= target:
                game_over = True
                final_winner = player.name
                break

        # Send round result to both players
        for client in self.session.clients:
            send_message(client.socket, Message(MessageType.ROUND_OVER, payload))

        if game_over:
            # Game over
            for client in self.session.clients:
                send_message(client.socket, Message(MessageType.GAME_OVER, {
                    "winner": final_winner,
                    "final_scores": payload["scores"],
                }))
            print(f"Game over! {final_winner} wins!")
            self.running = False
        else:
            print(f"Round over. Scores: {payload['scores']}")

    def _handle_ready(self, client: ClientConnection, msg: Message) -> None:
        """Handle READY message to start next round."""
        game = self.session.game
        if not game or game.phase != GamePhase.ROUND_OVER:
            send_message(client.socket, error_msg("Cannot ready now"))
            return

        # For simplicity, start new round when first READY received
        # (In a fuller implementation, wait for both players)
        game.new_round()
        game.deal()

        print("New round starting...")
        self._broadcast_state()
        self._notify_turns()

    def _handle_disconnect(self, client: ClientConnection) -> None:
        """Handle client disconnection."""
        print(f"Player disconnected: {client.player_name or 'unknown'}")

        try:
            self.selector.unregister(client.socket)
        except Exception:
            pass

        try:
            client.socket.close()
        except Exception:
            pass

        # Notify other player if game was in progress
        if self.session.is_full and client.player_idx >= 0:
            try:
                opponent = self.session.get_opponent(client.player_idx)
                send_message(opponent.socket, Message(MessageType.OPPONENT_DISCONNECTED, {
                    "message": f"{client.player_name} has disconnected. Game over."
                }))
            except Exception:
                pass

        self.running = False

    def _cleanup(self) -> None:
        """Clean up resources."""
        for client in self.session.clients:
            try:
                client.socket.close()
            except Exception:
                pass

        if self.server_socket:
            try:
                self.selector.unregister(self.server_socket)
                self.server_socket.close()
            except Exception:
                pass

        self.selector.close()


def main() -> None:
    """Entry point for gin-server command."""
    parser = argparse.ArgumentParser(description="Gin Rummy Network Server")
    parser.add_argument("--port", "-p", type=int, default=5555, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")

    args = parser.parse_args()

    server = GinRummyServer(host=args.host, port=args.port)
    server.start()


if __name__ == "__main__":
    main()
