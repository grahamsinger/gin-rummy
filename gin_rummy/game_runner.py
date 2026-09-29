"""Shared game turn execution logic for CLI and Simulator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

from gin_rummy.ai import (
    BasicAI,
    DiscardReasoning,
    DrawChoice,
    DrawReasoning,
    KnockReasoning,
    TurnReasoning,
)
from gin_rummy.game import Game, InvalidActionError, RoundResult
from gin_rummy.models import Card, Hand, Player, analyze_hand

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
    reasoning: TurnReasoning | None = None  # AI reasoning (if capture_reasoning=True)


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
    """Build game context for AIs that use it (``ai.needs_context``), else None.

    Args:
        game: Current game state.
        ai: The AI player.
        player_idx: Index of the AI player (0 or 1).
    """
    if ai.needs_context:
        return game.get_game_context(player_idx)
    return None


def get_ai_draw_decision(
    ai: BasicAI,
    hand: Hand,
    discard_top: Card | None,
    context: GameContext | None,
) -> DrawChoice:
    """Get AI's draw decision.

    Args:
        ai: The AI player.
        hand: Current hand.
        discard_top: Top of discard pile, or None.
        context: Game context, or None for AIs that don't use it.

    Returns:
        DrawChoice (DECK or DISCARD).
    """
    return ai.decide_draw(hand, discard_top, context)


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
    callbacks: TurnCallbacks | None = None,
    capture_reasoning: bool = False,
) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
    """Execute a full AI turn using shared game logic.

    This is the single source of truth for AI turn execution: the round
    runner's AISeat and the web session both call it. Telling the opponent
    what happened is the caller's job (round_runner relays the returned
    TurnActions to the other seat; the web session tells its AI directly).

    Args:
        game: Current game state.
        ai: The AI making decisions this turn.
        callbacks: Optional callbacks for side effects (UI, metrics, etc.).
        capture_reasoning: If True, capture detailed AI reasoning in actions.reasoning.

    Returns:
        Tuple of (TurnResult, TurnActions or None if deck exhausted, RoundResult or None if no knock).
    """
    if callbacks is None:
        callbacks = NoOpCallbacks()

    current = game.current_player
    current_idx = game.current_player_idx

    # Capture state before turn
    deadwood_before = current.hand.deadwood_total

    # Build context for AIs that use it
    context = get_ai_context(game, ai, current_idx)

    # AI decides where to draw (with optional reasoning capture)
    draw_reasoning: DrawReasoning | None = None
    if capture_reasoning:
        draw_reasoning = ai.decide_draw_with_reasoning(current.hand, game.top_of_discard, context)
        draw_choice = draw_reasoning.choice
    else:
        draw_choice = get_ai_draw_decision(ai, current.hand, game.top_of_discard, context)

    # actions.draw_source must say where the card actually came from
    if draw_choice == DrawChoice.DISCARD and not game.top_of_discard:
        draw_choice = DrawChoice.DECK  # nothing to pick up: execute_draw falls back to the deck

    # Execute draw
    card = execute_draw(game, draw_choice)
    if card is None:
        # Deck exhausted
        return TurnResult.DRAW, None, None

    # Callback: draw complete
    callbacks.on_draw(current, draw_choice, card)

    # AI decides what to discard (with optional reasoning capture)
    discard_reasoning: DiscardReasoning | None = None
    if capture_reasoning:
        discard_reasoning = ai.decide_discard_with_reasoning(current.hand)
        discard = discard_reasoning.card
    else:
        discard = ai.decide_discard(current.hand)

    # Rule: cannot discard the card just taken from the discard pile.
    # If the AI chose it anyway, substitute the best legal alternative.
    blocked = game.discard_blocked_card
    if discard == blocked:
        alternatives = [c for c in current.hand if c != blocked]
        discard = min(
            alternatives,
            key=lambda c: (
                calculate_post_discard_deadwood(current.hand, c),
                -c.deadwood_value,
            ),
        )
        if capture_reasoning and discard_reasoning is not None:
            discard_reasoning = DiscardReasoning(
                card=discard,
                reasoning=(
                    f"Fallback: {blocked} was just drawn from the discard pile "
                    f"and cannot be re-discarded; chose {discard} instead"
                ),
                factors=[f"Original choice {blocked} is illegal to discard"],
                options_considered=discard_reasoning.options_considered,
            )

    # Calculate post-discard deadwood for actions record
    deadwood_after = calculate_post_discard_deadwood(current.hand, discard)

    # Check if can knock based on post-discard deadwood (not current 11-card hand)
    can_knock_after_discard = deadwood_after <= game.knock_threshold

    # AI decides whether to knock (with optional reasoning capture)
    knock_reasoning: KnockReasoning | None = None
    if can_knock_after_discard:
        test_cards = [c for c in current.hand if c != discard]
        test_hand = Hand(test_cards)

        if capture_reasoning:
            knock_reasoning = ai.should_knock_with_reasoning(test_hand, context, pending_discard=discard)
            should_knock = knock_reasoning.should_knock
        else:
            should_knock = ai.should_knock(test_hand, context, pending_discard=discard)
    else:
        should_knock = False
        if capture_reasoning:
            # Create a knock reasoning for "can't knock"
            knock_reasoning = KnockReasoning(
                should_knock=False,
                reasoning=f"Cannot knock: deadwood={deadwood_after} > {game.knock_threshold}",
                score=None,
                factors=[f"Deadwood: {deadwood_after}", "Cannot knock: deadwood too high"],
            )

    # Build turn reasoning if capturing
    turn_reasoning: TurnReasoning | None = None
    if capture_reasoning and draw_reasoning and discard_reasoning:
        turn_reasoning = TurnReasoning(
            draw=draw_reasoning,
            discard=discard_reasoning,
            knock=knock_reasoning,
        )

    if should_knock and can_knock_after_discard:
        # Discard and knock (handles pile/history bookkeeping and validation)
        round_result = game.knock_with_discard(discard)

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
            reasoning=turn_reasoning,
        )
        callbacks.on_turn_complete(current, actions)

        return TurnResult.KNOCKED, actions, round_result
    else:
        # Execute discard
        game.discard(discard)

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
            reasoning=turn_reasoning,
        )
        callbacks.on_turn_complete(current, actions)

        return TurnResult.CONTINUE, actions, None
