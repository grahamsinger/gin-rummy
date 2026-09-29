"""One round loop for every blocking caller.

The CLI (vs AI and player vs player), the simulator, the scenario
generator and the trainer each had their own copy of the same loop: the
non-dealer's opening discard, then turns until someone knocks or the deck
runs out, telling the other player's AI what it saw along the way. They
differ only in who decides (a prompt or an AI), what happens around a turn
(display, metrics, experiences) and when to stop (the scenario quiz freezes
a hand mid-round). Those differences live in Seat implementations and the
`stop_when` predicate; the loop lives in `run_round`.

The web session stays request-driven and shares only the turn-level
pieces (`execute_ai_turn`, `TurnRecorder`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.game import Game, GamePhase, RoundResult
from gin_rummy.game_runner import TurnActions, TurnCallbacks, TurnResult, execute_ai_turn, get_ai_context
from gin_rummy.models import Card


class Seat(Protocol):
    """Whoever plays one side of the table."""

    def start_round(self, game: Game) -> None:
        """Called once per round, after the deal and before the opening discard."""
        ...

    def opening_discard(self, game: Game) -> Card:
        """Choose the non-dealer's opening discard from the 11-card hand (the runner applies it)."""
        ...

    def play_turn(self, game: Game) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
        """Play one full turn (draw, discard, maybe knock), like execute_ai_turn."""
        ...

    def observe_pickup(self, card: Card) -> None:
        """The opponent took `card` from the discard pile."""
        ...

    def observe_discard(self, card: Card) -> None:
        """The opponent discarded `card` (opening discard or a turn that did not knock)."""
        ...


class AISeat:
    """A seat played by an AI; opponent actions feed its tracking hooks."""

    def __init__(
        self,
        ai: BasicAI,
        callbacks: TurnCallbacks | None = None,
        capture_reasoning: bool = False,
    ) -> None:
        self.ai = ai
        self.callbacks = callbacks
        self.capture_reasoning = capture_reasoning

    def start_round(self, game: Game) -> None:
        self.ai.reset_for_new_hand()

    def opening_discard(self, game: Game) -> Card:
        context = get_ai_context(game, self.ai, game.current_player_idx)
        card = self.ai.decide_discard(game.current_player.hand, context)
        if self.callbacks is not None:
            self.callbacks.on_discard(game.current_player, card)
        return card

    def play_turn(self, game: Game) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
        return execute_ai_turn(game, self.ai, callbacks=self.callbacks, capture_reasoning=self.capture_reasoning)

    def observe_pickup(self, card: Card) -> None:
        self.ai.record_opponent_pickup(card)

    def observe_discard(self, card: Card) -> None:
        self.ai.record_opponent_discard(card)


@dataclass(frozen=True)
class RoundOutcome:
    """How a round ended.

    `result` is None only when `stop_when` halted the round early; then
    `ended_by` is CONTINUE and the game is still in the DRAWING phase.
    """

    result: RoundResult | None
    ended_by: TurnResult
    turns: int  # completed turns, not counting the opening discard


def run_round(
    game: Game,
    seats: Sequence[Seat],
    *,
    stop_when: Callable[[Game, int], bool] | None = None,
) -> RoundOutcome:
    """Play a dealt round to the end, or until `stop_when(game, turns)` says stop.

    The caller deals (and starts any hand tracking) first. `seats[i]`
    plays `game.players[i]`.
    """
    if game.phase not in (GamePhase.FIRST_DISCARD, GamePhase.DRAWING):
        raise ValueError(f"run_round needs a dealt game, not phase {game.phase.name}")
    if len(seats) != 2:
        raise ValueError("run_round needs exactly two seats")

    for seat in seats:
        seat.start_round(game)

    if game.phase == GamePhase.FIRST_DISCARD:
        opener = game.current_player_idx
        card = seats[opener].opening_discard(game)
        game.discard_to_start(card)
        seats[1 - opener].observe_discard(card)

    turns = 0
    while True:
        if stop_when is not None and stop_when(game, turns):
            return RoundOutcome(None, TurnResult.CONTINUE, turns)

        idx = game.current_player_idx
        result, actions, round_result = seats[idx].play_turn(game)
        turns += 1

        if actions is not None:
            other = seats[1 - idx]
            if actions.draw_source == DrawChoice.DISCARD:
                other.observe_pickup(actions.drawn_card)
            if not actions.did_knock:
                other.observe_discard(actions.discarded_card)

        if result == TurnResult.KNOCKED:
            return RoundOutcome(round_result, result, turns)
        if result == TurnResult.DRAW:
            return RoundOutcome(round_result or game.get_draw_result(), result, turns)
