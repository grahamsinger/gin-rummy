"""Game logic and state machine for Gin Rummy."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

from gin_rummy.models import Card, Deck, Player, Suit
from gin_rummy.models.melds import calculate_layoff
from gin_rummy.config import get_config

if TYPE_CHECKING:
    from gin_rummy.context import GameContext


class GamePhase(Enum):
    """Phases of a Gin Rummy game."""

    DEALING = auto()
    FIRST_DISCARD = auto()  # Non-dealer must discard from 11 cards
    DRAWING = auto()
    DISCARDING = auto()
    KNOCKED = auto()
    ROUND_OVER = auto()


class InvalidActionError(Exception):
    """Raised when an action is invalid for the current game state."""

    pass


@dataclass
class RoundResult:
    """Result of a completed round."""

    winner: Player | None  # None if draw
    loser: Player | None
    points: int
    is_gin: bool
    is_undercut: bool
    is_draw: bool
    knocker: Player | None = None  # Who knocked (None if draw)
    winner_deadwood: int = 0
    loser_deadwood: int = 0
    layoff_cards: list[Card] | None = None  # Cards defender laid off (None if gin/draw)
    defender_deadwood_before_layoff: int = 0  # Defender's deadwood before layoff


class Game:
    """Gin Rummy game state and logic."""

    def __init__(
        self,
        player1_name: str,
        player2_name: str,
        is_oklahoma_gin: bool = False,
        spade_doubling_enabled: bool = False,
    ) -> None:
        """Create a new game with two players.

        Args:
            player1_name: Name of first player.
            player2_name: Name of second player.
            is_oklahoma_gin: Whether to use Oklahoma Gin rules.
            spade_doubling_enabled: Whether to double points when upcard is a spade.
        """
        # Load game rules from config
        config = get_config()
        self._base_knock_threshold = config.game_rules.knock_threshold
        self.gin_bonus = config.game_rules.gin_bonus
        self.undercut_bonus = config.game_rules.undercut_bonus
        self.min_deck_cards = config.game_rules.min_deck_cards

        # Oklahoma Gin settings
        self.is_oklahoma_gin = is_oklahoma_gin
        self.spade_doubling_enabled = spade_doubling_enabled
        self.upcard: Card | None = None

        self.players: tuple[Player, Player] = (
            Player(player1_name),
            Player(player2_name),
        )
        self.deck = Deck()
        self.discard_pile: list[Card] = []
        self.phase = GamePhase.DEALING
        self.current_player_idx = 0
        # Randomize starting dealer to eliminate positional advantage
        self.dealer_idx = random.randint(0, 1)
        self._card_drawn_this_turn: Card | None = None

        # Assist mode tracking
        self._discard_pickups: dict[str, list[Card]] = {
            player1_name: [],
            player2_name: [],
        }
        self._discard_rediscards: dict[str, list[Card]] = {
            player1_name: [],
            player2_name: [],
        }
        self._discard_history: list[Card] = []

    @property
    def knock_threshold(self) -> int:
        """Get current knock threshold (dynamic for Oklahoma Gin)."""
        if not self.is_oklahoma_gin or self.upcard is None:
            return self._base_knock_threshold

        # Oklahoma Gin - threshold based on upcard rank
        rank_value = self.upcard.rank.value
        if rank_value == 1:  # Ace
            return 0
        elif rank_value <= 10:
            return rank_value
        else:  # J, Q, K
            return 10

    @property
    def current_player(self) -> Player:
        """Return the player whose turn it is."""
        return self.players[self.current_player_idx]

    @property
    def opponent(self) -> Player:
        """Return the player who is not currently playing."""
        return self.players[1 - self.current_player_idx]

    @property
    def dealer(self) -> Player:
        """Return the dealer for the current round."""
        return self.players[self.dealer_idx]

    @property
    def non_dealer(self) -> Player:
        """Return the non-dealer for the current round."""
        return self.players[1 - self.dealer_idx]

    @property
    def top_of_discard(self) -> Card | None:
        """Return the top card of the discard pile, or None if empty."""
        return self.discard_pile[-1] if self.discard_pile else None

    @property
    def discard_history(self) -> list[Card]:
        """Return all cards discarded this hand (for assist mode)."""
        return self._discard_history.copy()

    def get_player_pickups(self, player_name: str) -> list[Card]:
        """Return cards a player picked from discard pile this hand."""
        return self._discard_pickups.get(player_name, []).copy()

    def get_game_context(self, player_idx: int) -> "GameContext":
        """Build game context for AI decision-making.

        Creates a snapshot of the current game state from the perspective
        of the specified player.

        Args:
            player_idx: 0 or 1, which player's perspective.

        Returns:
            GameContext with all relevant state for AI decisions.
        """
        from gin_rummy.context import GameContext, KnownCards

        player = self.players[player_idx]
        opponent = self.players[1 - player_idx]

        # Calculate deck position (31 cards remain after deal)
        # After deal: 21 in hands + 0-1 in discard + rest in deck
        max_deck_size = 31  # 52 - 21 (dealt to hands)
        deck_position_pct = 1 - (len(self.deck) / max_deck_size) if max_deck_size > 0 else 0

        # Get target score from config
        config = get_config()
        target_score = config.game_rules.target_score

        # Build unified card location tracking
        opponent_pickups = set(self._discard_pickups.get(opponent.name, []))
        opponent_rediscards = set(self._discard_rediscards.get(opponent.name, []))
        opponent_hand_known = opponent_pickups - opponent_rediscards

        # Discard pile: top card is available, rest are buried
        # Exclude cards opponent picked up (they're in opponent's hand, not buried)
        discard_top = self.discard_pile[-1] if self.discard_pile else None
        discard_buried_candidates = frozenset(self._discard_history[:-1]) if len(self._discard_history) > 1 else frozenset()
        discard_buried = discard_buried_candidates - opponent_hand_known

        known_cards = KnownCards(
            my_hand=frozenset(player.hand),
            opponent_hand_known=frozenset(opponent_hand_known),
            discard_top=discard_top,
            discard_buried=discard_buried,
        )

        return GameContext(
            deck_remaining=len(self.deck),
            deck_position_pct=deck_position_pct,
            my_score=player.score,
            opponent_score=opponent.score,
            known_cards=known_cards,
            discard_history=self._discard_history.copy(),
            opponent_pickups=self._discard_pickups.get(opponent.name, []).copy(),
            my_pickups=self._discard_pickups.get(player.name, []).copy(),
            target_score=target_score,
        )

    @property
    def can_knock(self) -> bool:
        """Return True if current player can knock (deadwood <= threshold)."""
        return self.current_player.hand.deadwood_total <= self.knock_threshold

    def deal(self) -> None:
        """Deal cards to start a round.

        - Shuffles deck
        - Deals 10 cards to each player
        - Deals 11th card to non-dealer
        - Sets phase to FIRST_DISCARD
        """
        if self.phase != GamePhase.DEALING:
            raise InvalidActionError("Can only deal in DEALING phase")

        # Reset for new round
        self.deck = Deck()
        self.deck.shuffle()
        self.discard_pile = []

        # Reset assist tracking
        for player in self.players:
            self._discard_pickups[player.name] = []
            self._discard_rediscards[player.name] = []
        self._discard_history = []

        for player in self.players:
            player.reset_hand()

        # Deal 10 cards to each player
        for _ in range(10):
            for player in self.players:
                player.hand.add(self.deck.draw())

        if self.is_oklahoma_gin:
            # Oklahoma Gin: turn upcard, becomes first discard
            self.upcard = self.deck.draw()
            self.discard_pile.append(self.upcard)
            self._discard_history.append(self.upcard)

            # Non-dealer goes first (already indexed)
            self.current_player_idx = 1 - self.dealer_idx
            self.phase = GamePhase.DRAWING  # Skip FIRST_DISCARD
        else:
            # Standard Gin: deal 11th card to non-dealer
            self.non_dealer.hand.add(self.deck.draw())

            # Non-dealer goes first (to discard)
            self.current_player_idx = 1 - self.dealer_idx
            self.phase = GamePhase.FIRST_DISCARD

    def discard_to_start(self, card: Card) -> None:
        """Non-dealer's opening discard from their 11 cards.

        Args:
            card: Card to discard.

        Raises:
            InvalidActionError: If not in FIRST_DISCARD phase or card not in hand.
        """
        if self.phase != GamePhase.FIRST_DISCARD:
            raise InvalidActionError("Can only discard to start in FIRST_DISCARD phase")

        if card not in self.current_player.hand:
            raise InvalidActionError(f"{card} is not in your hand")

        self.current_player.hand.remove(card)
        self.discard_pile.append(card)
        self._discard_history.append(card)

        # Switch to dealer's turn - non-dealer doesn't go again consecutively
        self.current_player_idx = self.dealer_idx
        self.phase = GamePhase.DRAWING

    def draw_from_deck(self) -> Card:
        """Current player draws from deck.

        Returns:
            The drawn card.

        Raises:
            InvalidActionError: If not in DRAWING phase or deck too low.
        """
        if self.phase != GamePhase.DRAWING:
            raise InvalidActionError("Can only draw in DRAWING phase")

        # Check if deck is at minimum (round ends in draw)
        if len(self.deck) <= self.min_deck_cards:
            self.phase = GamePhase.ROUND_OVER
            raise InvalidActionError(
                f"Deck has only {len(self.deck)} cards - round ends in draw"
            )

        card = self.deck.draw()
        self.current_player.hand.add(card)
        self._card_drawn_this_turn = card
        self.phase = GamePhase.DISCARDING
        return card

    def draw_from_discard(self) -> Card:
        """Current player takes the top card from discard pile.

        Returns:
            The drawn card.

        Raises:
            InvalidActionError: If not in DRAWING phase or discard pile empty.
        """
        if self.phase != GamePhase.DRAWING:
            raise InvalidActionError("Can only draw in DRAWING phase")

        if not self.discard_pile:
            raise InvalidActionError("Discard pile is empty")

        card = self.discard_pile.pop()
        self.current_player.hand.add(card)
        self._card_drawn_this_turn = card
        self._discard_pickups[self.current_player.name].append(card)
        self.phase = GamePhase.DISCARDING
        return card

    def discard(self, card: Card) -> None:
        """Current player discards a card and ends their turn.

        Args:
            card: Card to discard.

        Raises:
            InvalidActionError: If not in DISCARDING phase, card not in hand,
                               or trying to discard the card just drawn from discard.
        """
        if self.phase != GamePhase.DISCARDING:
            raise InvalidActionError("Can only discard in DISCARDING phase")

        if card not in self.current_player.hand:
            raise InvalidActionError(f"{card} is not in your hand")

        # Cannot discard the same card just picked up from discard pile
        if card == self._card_drawn_this_turn and len(self.discard_pile) > 0:
            # Only enforce if we drew from discard (discard pile would have been smaller)
            # Actually, we need to track WHERE we drew from
            pass  # For now, allow it - tracking draw source adds complexity

        # Track if this card was previously picked up (now being re-discarded)
        player_name = self.current_player.name
        if card in self._discard_pickups[player_name]:
            self._discard_rediscards[player_name].append(card)

        self.current_player.hand.remove(card)
        self.discard_pile.append(card)
        self._discard_history.append(card)
        self._card_drawn_this_turn = None

        # Switch to opponent's turn
        self.current_player_idx = 1 - self.current_player_idx
        self.phase = GamePhase.DRAWING

    def knock(self) -> RoundResult:
        """Current player knocks to end the round.

        Returns:
            RoundResult with winner, points, and flags.

        Raises:
            InvalidActionError: If not in DISCARDING phase or deadwood > 10.
        """
        if self.phase != GamePhase.DISCARDING:
            raise InvalidActionError("Can only knock in DISCARDING phase")

        knocker = self.current_player
        defender = self.opponent

        if knocker.hand.deadwood_total > self.knock_threshold:
            raise InvalidActionError(
                f"Cannot knock with {knocker.hand.deadwood_total} deadwood "
                f"(must be {self.knock_threshold} or less)"
            )

        knocker_deadwood = knocker.hand.deadwood_total

        self.phase = GamePhase.KNOCKED

        # Determine outcome
        is_gin = knocker_deadwood == 0

        # Track layoff information
        layoff_cards: list[Card] | None = None
        defender_deadwood_before_layoff = defender.hand.deadwood_total

        if is_gin:
            # No laying off allowed on gin - use defender's raw deadwood
            defender_deadwood = defender_deadwood_before_layoff
        else:
            # Defender can lay off cards on knocker's melds
            knocker_analysis = knocker.hand.analyze()
            layoff_result = calculate_layoff(
                list(defender.hand), knocker_analysis.melds
            )
            defender_deadwood = layoff_result.deadwood_after
            layoff_cards = layoff_result.layoff_cards if layoff_result.layoff_cards else None

        is_undercut = not is_gin and defender_deadwood <= knocker_deadwood

        if is_gin:
            # Gin: knocker wins bonus + defender's deadwood
            points = self.gin_bonus + defender_deadwood
            winner = knocker
            loser = defender
        elif is_undercut:
            # Undercut: defender wins bonus + difference
            points = self.undercut_bonus + (knocker_deadwood - defender_deadwood)
            winner = defender
            loser = knocker
        else:
            # Normal knock: knocker wins the difference
            points = knocker_deadwood - defender_deadwood
            # Wait, if knocker has less deadwood, difference is negative
            # knocker wins if their deadwood is lower
            points = defender_deadwood - knocker_deadwood
            winner = knocker
            loser = defender

        # Apply spade doubling for Oklahoma Gin
        if self.is_oklahoma_gin and self.spade_doubling_enabled and self.upcard:
            if self.upcard.suit == Suit.SPADES:
                points *= 2  # Double the points for spades

        winner.score += points
        self.phase = GamePhase.ROUND_OVER

        return RoundResult(
            winner=winner,
            loser=loser,
            points=points,
            is_gin=is_gin,
            is_undercut=is_undercut,
            is_draw=False,
            knocker=knocker,
            winner_deadwood=winner.hand.deadwood_total,
            loser_deadwood=loser.hand.deadwood_total,
            layoff_cards=layoff_cards,
            defender_deadwood_before_layoff=defender_deadwood_before_layoff,
        )

    def new_round(self) -> None:
        """Start a new round, alternating dealer."""
        self.dealer_idx = 1 - self.dealer_idx
        self.phase = GamePhase.DEALING
        self._card_drawn_this_turn = None

    def get_draw_result(self) -> RoundResult:
        """Get result for a draw (deck exhausted).

        Returns:
            RoundResult indicating a draw.
        """
        return RoundResult(
            winner=None,
            loser=None,
            points=0,
            is_gin=False,
            is_undercut=False,
            is_draw=True,
        )
