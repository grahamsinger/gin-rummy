"""Network protocol for Gin Rummy multiplayer.

Wire format: Length-prefixed JSON messages.
[4 bytes: message length (big-endian uint32)][JSON payload]
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from gin_rummy.card import Card, Rank, Suit


class MessageType(str, Enum):
    """Message types for client-server communication."""

    # Client -> Server
    JOIN = "JOIN"
    DRAW = "DRAW"
    DISCARD = "DISCARD"
    KNOCK = "KNOCK"
    FIRST_DISCARD = "FIRST_DISCARD"
    READY = "READY"
    PING = "PING"
    QUIT = "QUIT"

    # Server -> Client
    WELCOME = "WELCOME"
    WAITING = "WAITING"
    GAME_START = "GAME_START"
    STATE = "STATE"
    YOUR_TURN = "YOUR_TURN"
    OPPONENT_TURN = "OPPONENT_TURN"
    DRAW_RESULT = "DRAW_RESULT"
    OPPONENT_DREW = "OPPONENT_DREW"
    DISCARD_RESULT = "DISCARD_RESULT"
    OPPONENT_DISCARDED = "OPPONENT_DISCARDED"
    KNOCK_RESULT = "KNOCK_RESULT"
    ROUND_OVER = "ROUND_OVER"
    GAME_OVER = "GAME_OVER"
    ERROR = "ERROR"
    OPPONENT_DISCONNECTED = "OPPONENT_DISCONNECTED"
    PONG = "PONG"


@dataclass
class Message:
    """A network message with type and payload."""

    type: MessageType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Create from dictionary (JSON deserialization)."""
        return cls(
            type=MessageType(data["type"]),
            payload=data.get("payload", {}),
        )


# Card encoding: Rank short name + Suit letter
# Examples: "AS" = Ace of Spades, "10H" = 10 of Hearts, "KC" = King of Clubs

SUIT_TO_LETTER = {
    Suit.SPADES: "S",
    Suit.HEARTS: "H",
    Suit.DIAMONDS: "D",
    Suit.CLUBS: "C",
}

LETTER_TO_SUIT = {v: k for k, v in SUIT_TO_LETTER.items()}

RANK_TO_STR = {
    Rank.ACE: "A",
    Rank.TWO: "2",
    Rank.THREE: "3",
    Rank.FOUR: "4",
    Rank.FIVE: "5",
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "10",
    Rank.JACK: "J",
    Rank.QUEEN: "Q",
    Rank.KING: "K",
}

STR_TO_RANK = {v: k for k, v in RANK_TO_STR.items()}


def card_to_str(card: Card) -> str:
    """Convert Card to wire format string.

    Examples: Card(ACE, SPADES) -> "AS", Card(TEN, HEARTS) -> "10H"
    """
    return f"{RANK_TO_STR[card.rank]}{SUIT_TO_LETTER[card.suit]}"


def str_to_card(s: str) -> Card:
    """Parse wire format string to Card.

    Examples: "AS" -> Card(ACE, SPADES), "10H" -> Card(TEN, HEARTS)
    """
    s = s.upper()
    # Handle "10" specially (two-char rank)
    if s.startswith("10"):
        rank_str = "10"
        suit_str = s[2:]
    else:
        rank_str = s[:-1]
        suit_str = s[-1]

    if rank_str not in STR_TO_RANK:
        raise ValueError(f"Invalid rank: {rank_str}")
    if suit_str not in LETTER_TO_SUIT:
        raise ValueError(f"Invalid suit: {suit_str}")

    return Card(STR_TO_RANK[rank_str], LETTER_TO_SUIT[suit_str])


def cards_to_str_list(cards: list[Card]) -> list[str]:
    """Convert list of Cards to wire format strings."""
    return [card_to_str(c) for c in cards]


def str_list_to_cards(strings: list[str]) -> list[Card]:
    """Parse list of wire format strings to Cards."""
    return [str_to_card(s) for s in strings]


def _recv_exact(sock, n: int) -> bytes:
    """Receive exactly n bytes from socket."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data


def send_message(sock, msg: Message) -> None:
    """Send a length-prefixed JSON message over socket."""
    data = json.dumps(msg.to_dict()).encode("utf-8")
    length = len(data)
    sock.sendall(struct.pack(">I", length))
    sock.sendall(data)


def recv_message(sock) -> Message:
    """Receive a length-prefixed JSON message from socket."""
    length_data = _recv_exact(sock, 4)
    length = struct.unpack(">I", length_data)[0]

    # Sanity check to prevent memory exhaustion
    if length > 65536:
        raise ValueError(f"Message too large: {length} bytes")

    data = _recv_exact(sock, length)
    msg_dict = json.loads(data.decode("utf-8"))
    return Message.from_dict(msg_dict)


# Helper functions for creating common messages


def join_msg(player_name: str) -> Message:
    """Create JOIN message."""
    return Message(MessageType.JOIN, {"player_name": player_name})


def draw_msg(source: str) -> Message:
    """Create DRAW message. source is 'deck' or 'discard'."""
    return Message(MessageType.DRAW, {"source": source})


def discard_msg(card: Card) -> Message:
    """Create DISCARD message."""
    return Message(MessageType.DISCARD, {"card": card_to_str(card)})


def knock_msg(card: Card) -> Message:
    """Create KNOCK message."""
    return Message(MessageType.KNOCK, {"card": card_to_str(card)})


def first_discard_msg(card: Card) -> Message:
    """Create FIRST_DISCARD message."""
    return Message(MessageType.FIRST_DISCARD, {"card": card_to_str(card)})


def ready_msg() -> Message:
    """Create READY message."""
    return Message(MessageType.READY)


def error_msg(message: str, code: str = "ERROR") -> Message:
    """Create ERROR message."""
    return Message(MessageType.ERROR, {"message": message, "code": code})
