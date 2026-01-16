"""Shared game turn execution logic for CLI and Simulator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

from gin_rummy.ai import BasicAI, ContextAwareAI, DrawChoice
from gin_rummy.models import Card, Hand, Player, analyze_hand
from gin_rummy.game import Game, InvalidActionError, RoundResult

if TYPE_CHECKING:
    from gin_rummy.context import GameContext


class TurnResult(Enum):
    """Result of a turn."""

    CONTINUE = auto()  # Round continues
    KNOCKED = auto()  # Player knocked, round over
    DRAW = auto()  # Deck exhausted, round is a draw


@dataclass
class TurnActions:
    """Captures all actions taken during a turn."""

    draw_source: DrawChoice
    drawn_card: Card
    discarded_card: Card
    did_knock: bool
    deadwood_before: int
    deadwood_after: int


class TurnCallbacks(Protocol):
    """Protocol for turn side effect callbacks.

    Implementations can provide UI output, metrics tracking, database logging, etc.
    All methods are optional - implement only what you need.
    """

    def on_draw(self, player: Player, source: DrawChoice, card: Card) -> None:
        """Called after a card is drawn."""
        ...

    def on_discard(self, player: Player, card: Card) -> None:
        """Called after a card is discarded (non-knock)."""
        ...

    def on_knock(self, player: Player, discard: Card, deadwood: int, result: RoundResult) -> None:
        """Called when player knocks."""
        ...

    def on_turn_complete(self, player: Player, actions: TurnActions) -> None:
        """Called after turn is fully complete."""
        ...


class NoOpCallbacks:
    """Default callbacks that do nothing."""

    def on_draw(self, player: Player, source: DrawChoice, card: Card) -> None:
        pass

    def on_discard(self, player: Player, card: Card) -> None:
        pass

    def on_knock(self, player: Player, discard: Card, deadwood: int, result: RoundResult) -> None:
        pass

    def on_turn_complete(self, player: Player, actions: TurnActions) -> None:
        pass


def get_ai_context(game: Game, ai: BasicAI, player_idx: int) -> GameContext | None:
    """Build game context for ContextAwareAI, or return None for BasicAI.

    Args:
        game: Current game state.
        ai: The AI player.
        player_idx: Index of the AI player (0 or 1).

    Returns:
        GameContext if ai is ContextAwareAI, else None.
    """
    if isinstance(ai, ContextAwareAI):
        return game.get_game_context(player_idx)
    return None


def get_ai_draw_decision(
    ai: BasicAI,
    hand: Hand,
    discard_top: Card | None,
    context: GameContext | None,
) -> DrawChoice:
    """Get AI's draw decision, handling context appropriately.

    Args:
        ai: The AI player.
        hand: Current hand.
        discard_top: Top of discard pile, or None.
        context: Game context for ContextAwareAI, or None.

    Returns:
        DrawChoice (DECK or DISCARD).
    """
    if isinstance(ai, ContextAwareAI) and context is not None:
        return ai.decide_draw(hand, discard_top, context)
    return ai.decide_draw(hand, discard_top)


def execute_draw(game: Game, draw_choice: DrawChoice) -> Card | None:
    """Execute the draw action.

    Args:
        game: Current game state.
        draw_choice: Where to draw from.

    Returns:
        The drawn card, or None if deck exhausted.
    """
    if draw_choice == DrawChoice.DISCARD and game.top_of_discard:
        return game.draw_from_discard()
    else:
        try:
            return game.draw_from_deck()
        except InvalidActionError:
            return None


def record_opponent_pickup(other_ai: BasicAI | None, card: Card) -> None:
    """Record that opponent picked up a card from discard.

    Args:
        other_ai: The other AI (opponent), or None.
        card: The card that was picked up.
    """
    if isinstance(other_ai, ContextAwareAI):
        other_ai.record_opponent_pickup(card)


def record_opponent_discard(other_ai: BasicAI | None, card: Card) -> None:
    """Record that opponent discarded a card.

    Args:
        other_ai: The other AI (opponent), or None.
        card: The card that was discarded.
    """
    if isinstance(other_ai, ContextAwareAI):
        other_ai.record_opponent_discard(card)


def calculate_post_discard_deadwood(hand: Hand, discard: Card) -> int:
    """Calculate deadwood after discarding a card.

    Args:
        hand: Current hand (11 cards).
        discard: Card to be discarded.

    Returns:
        Deadwood value after discard.
    """
    test_cards = [c for c in hand if c != discard]
    return analyze_hand(test_cards).deadwood_value


def execute_ai_turn(
    game: Game,
    ai: BasicAI,
    other_ai: BasicAI | None = None,
    callbacks: TurnCallbacks | None = None,
) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
    """Execute a full AI turn using shared game logic.

    This is the single source of truth for AI turn execution.
    Both CLI and Simulator should use this function.

    Args:
        game: Current game state.
        ai: The AI making decisions this turn.
        other_ai: The opponent AI (for tracking pickups/discards), or None.
        callbacks: Optional callbacks for side effects (UI, metrics, etc.).

    Returns:
        Tuple of (TurnResult, TurnActions or None if deck exhausted, RoundResult or None if no knock).
    """
    if callbacks is None:
        callbacks = NoOpCallbacks()

    current = game.current_player
    current_idx = game.current_player_idx

    # Capture state before turn
    deadwood_before = current.hand.deadwood_total

    # Build context for ContextAwareAI
    context = get_ai_context(game, ai, current_idx)

    # AI decides where to draw
    draw_choice = get_ai_draw_decision(ai, current.hand, game.top_of_discard, context)

    # Track top of discard before draw (for opponent pickup tracking)
    discard_top_before = game.top_of_discard

    # Execute draw
    card = execute_draw(game, draw_choice)
    if card is None:
        # Deck exhausted
        return TurnResult.DRAW, None, None

    # Record pickup for opponent tracking
    if draw_choice == DrawChoice.DISCARD and discard_top_before:
        record_opponent_pickup(other_ai, discard_top_before)

    # Callback: draw complete
    callbacks.on_draw(current, draw_choice, card)

    # AI decides what to discard and whether to knock
    discard, should_knock = ai.make_turn_decision(
        current.hand, game.top_of_discard, card
    )

    # Calculate post-discard deadwood for actions record
    deadwood_after = calculate_post_discard_deadwood(current.hand, discard)

    # Check if can knock based on post-discard deadwood (not current 11-card hand)
    can_knock_after_discard = deadwood_after <= game.knock_threshold

    if should_knock and can_knock_after_discard:
        # First discard the card (game.knock expects 10-card hand)
        current.hand.remove(discard)
        game.discard_pile.append(discard)

        # Execute knock and capture result
        round_result = game.knock()

        # Callback: knock (called after knock so round result is available)
        callbacks.on_knock(current, discard, deadwood_after, round_result)

        # Build actions record
        actions = TurnActions(
            draw_source=draw_choice,
            drawn_card=card,
            discarded_card=discard,
            did_knock=True,
            deadwood_before=deadwood_before,
            deadwood_after=deadwood_after,
        )
        callbacks.on_turn_complete(current, actions)

        return TurnResult.KNOCKED, actions, round_result
    else:
        # Execute discard
        game.discard(discard)

        # Record discard for opponent tracking
        record_opponent_discard(other_ai, discard)

        # Callback: discard
        callbacks.on_discard(current, discard)

        # Build actions record
        actions = TurnActions(
            draw_source=draw_choice,
            drawn_card=card,
            discarded_card=discard,
            did_knock=False,
            deadwood_before=deadwood_before,
            deadwood_after=current.hand.deadwood_total,
        )
        callbacks.on_turn_complete(current, actions)

        return TurnResult.CONTINUE, actions, None
