"""Snapshot of the game state an AI decides from: where every card is, scores, deck position."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from gin_rummy.models import Card
from gin_rummy.models.outs import OutsAnalysis


class CardLocation(Enum):
    """Where a card is located from a player's perspective."""

    MY_HAND = auto()  # In my current hand
    OPPONENT_HAND_KNOWN = auto()  # Opponent picked from discard, not re-discarded
    DISCARD_TOP = auto()  # Top of discard pile (available to take)
    DISCARD_BURIED = auto()  # Previously discarded, now buried under other cards
    UNKNOWN = auto()  # In deck or opponent's initial hand (can't distinguish)


@dataclass
class KnownCards:
    """Unified card location tracking from one player's perspective.

    Tracks where all cards are located based on observable game events.
    This is the single source of truth for card availability.
    """

    my_hand: frozenset[Card]
    opponent_hand_known: frozenset[Card]  # Picked from discard, not re-discarded
    discard_top: Card | None  # Available to take
    discard_buried: frozenset[Card]  # Previously discarded, now inaccessible

    def get_location(self, card: Card) -> CardLocation:
        """Determine where a card is located."""
        if card in self.my_hand:
            return CardLocation.MY_HAND
        if card in self.opponent_hand_known:
            return CardLocation.OPPONENT_HAND_KNOWN
        if card == self.discard_top:
            return CardLocation.DISCARD_TOP
        if card in self.discard_buried:
            return CardLocation.DISCARD_BURIED
        return CardLocation.UNKNOWN

    @property
    def dead_cards(self) -> frozenset[Card]:
        """Cards in the discard pile (buried, not available to draw).

        Note: Does NOT include discard_top (that's available) or my_hand.
        """
        return self.discard_buried

    @property
    def unavailable_cards(self) -> frozenset[Card]:
        """Cards that can never be drawn: buried discards plus cards known
        to be in the opponent's hand. Use this for outs calculations -
        an out sitting in the opponent's hand is not live.
        """
        return self.discard_buried | self.opponent_hand_known


@dataclass
class GameContext:
    """Snapshot of game state for AI decision-making."""

    # Deck state
    deck_remaining: int
    deck_position_pct: float  # 0.0 = full deck, 1.0 = nearly empty

    # Score context (required fields)
    my_score: int
    opponent_score: int

    # Unified card tracking
    known_cards: KnownCards | None = None

    # Legacy fields for backwards compatibility (OpponentModel uses these)
    discard_history: list[Card] = field(default_factory=list)
    opponent_pickups: list[Card] = field(default_factory=list)
    my_pickups: list[Card] = field(default_factory=list)

    target_score: int = 100

    # Knock threshold in effect (dynamic under Oklahoma Gin rules)
    knock_threshold: int = 10

    # The card the player drew this turn (None before drawing, or for the
    # player not on turn); set for the discard and knock decisions
    drawn_card: Card | None = None

    # Current hand analysis (set by AI after construction)
    my_outs: OutsAnalysis | None = None

    @property
    def dead_cards(self) -> set[Card]:
        """All known unavailable cards. Uses KnownCards if available."""
        if self.known_cards:
            return set(self.known_cards.dead_cards)
        # Fallback for backwards compatibility
        return set(self.discard_history)

    @property
    def unavailable_cards(self) -> set[Card]:
        """Cards that cannot be drawn: buried discards plus cards known to
        be in the opponent's hand. Prefer this over dead_cards for outs.
        """
        if self.known_cards:
            return set(self.known_cards.unavailable_cards)
        return set(self.discard_history)

    @property
    def score_differential(self) -> int:
        """Positive = leading, negative = trailing."""
        return self.my_score - self.opponent_score

    @property
    def points_to_win(self) -> int:
        """Points I need to win."""
        return max(0, self.target_score - self.my_score)

    @property
    def opponent_points_to_win(self) -> int:
        """Points opponent needs to win."""
        return max(0, self.target_score - self.opponent_score)
