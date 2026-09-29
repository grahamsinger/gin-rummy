"""Terminal seats and rounds: the AI's turn on screen, and a round vs AI or player vs player."""

from __future__ import annotations

import time

from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.cli.prompts import play_human_first_discard, play_human_turn
from gin_rummy.cli.render import clear_screen, display_game_state, display_round_result
from gin_rummy.config import get_config
from gin_rummy.db import GameTracker
from gin_rummy.game import Game, RoundResult
from gin_rummy.game_runner import (
    TurnActions,
    TurnResult,
    execute_ai_turn,
    get_ai_context,
)
from gin_rummy.models import Card, Player
from gin_rummy.round_runner import AISeat, Seat, run_round
from gin_rummy.tracking import TurnRecord, TurnRecorder, TurnSnapshot


def play_ai_first_discard(game: Game, ai: BasicAI) -> Card:
    """Let the AI choose the opening discard (the round runner applies it)."""
    delay = get_config().display.ai_turn_delay
    ai_name = game.current_player.name
    print(f"\n{ai_name} is choosing a card to discard...")
    time.sleep(delay * 2)  # Slightly longer for first discard

    context = get_ai_context(game, ai, game.current_player_idx)
    discard = ai.decide_discard(game.current_player.hand, context)
    print(f"{ai_name} discarded {discard}")
    time.sleep(delay)
    return discard


class CLITurnCallbacks:
    """Callbacks for AI turn side effects in CLI mode.

    Handles UI output (print statements, delays) and database tracking.
    """

    def __init__(
        self,
        game: Game,
        recorder: TurnRecorder,
        delay: float,
        snapshot: TurnSnapshot,
    ) -> None:
        self.game = game
        self.recorder = recorder
        self.delay = delay
        self.snapshot = snapshot

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

    def on_knock(self, player: Player, discard: Card, deadwood: int, result: RoundResult) -> None:
        """Print knock message, display round result, and add delay."""
        print(f"{player.name} knocks!")
        time.sleep(self.delay)
        display_round_result(self.game, result)

    def on_turn_complete(self, player: Player, actions: TurnActions) -> None:
        """Record the turn (and the AI's reasoning) to the database."""
        self.recorder.write(TurnRecord.from_actions(player, self.snapshot, actions))


def play_ai_turn(
    game: Game,
    ai: BasicAI,
    human_player_idx: int,
    tracker: GameTracker | None = None,
) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
    """Play an AI turn using shared game runner logic.

    Args:
        game: Current game state.
        ai: The AI making decisions.
        human_player_idx: Index of human player (unused, kept for API compatibility).
        tracker: Optional database tracker for recording turns.

    Returns:
        (TurnResult, TurnActions, RoundResult) as execute_ai_turn returns them.
    """
    config = get_config()
    delay = config.display.ai_turn_delay
    current = game.current_player

    # Initial delay before AI acts
    time.sleep(delay)

    # Capture state before turn (needed for database tracking)
    recorder = TurnRecorder(tracker)
    callbacks = CLITurnCallbacks(game, recorder, delay, TurnSnapshot.of(current))

    # Execute the turn using shared game logic; capture reasoning when the
    # DB stores AI decisions (same rows the web UI records)
    return execute_ai_turn(game, ai, callbacks=callbacks, capture_reasoning=recorder.track_ai_decisions)


def finish_round(
    game: Game,
    turn_result: TurnResult,
    round_result: RoundResult | None,
    tracker: GameTracker | None,
) -> None:
    """Record the round outcome and print the draw message, if any."""
    if tracker and round_result is not None:
        tracker.end_hand_from_result(round_result)

    if turn_result == TurnResult.DRAW:
        print("\nRound ended in a DRAW (deck exhausted)")

    input("\nPress Enter to continue...")


class CLIHumanSeat:
    """A human at the terminal. In player-vs-player mode each turn starts with a hand-over prompt."""

    def __init__(self, player_idx: int, tracker: GameTracker | None, pause_before_turn: bool = False) -> None:
        self.player_idx = player_idx
        self.tracker = tracker
        self.pause_before_turn = pause_before_turn

    def start_round(self, game: Game) -> None:
        pass

    def opening_discard(self, game: Game) -> Card:
        clear_screen()
        return play_human_first_discard(game, self.player_idx)

    def play_turn(self, game: Game) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
        if self.pause_before_turn:
            input("\nPress Enter for next player's turn...")
        return play_human_turn(game, self.player_idx, self.tracker)

    def observe_pickup(self, card: Card) -> None:
        pass

    def observe_discard(self, card: Card) -> None:
        pass


class CLIAISeat(AISeat):
    """The computer opponent: shows the table before it acts and records its turns."""

    def __init__(self, ai: BasicAI, human_player_idx: int, tracker: GameTracker | None) -> None:
        super().__init__(ai)
        self.human_player_idx = human_player_idx
        self.tracker = tracker

    def opening_discard(self, game: Game) -> Card:
        clear_screen()
        display_game_state(game, self.human_player_idx, turn_player_name=game.current_player.name)
        return play_ai_first_discard(game, self.ai)

    def play_turn(self, game: Game) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
        clear_screen()
        display_game_state(game, self.human_player_idx, turn_player_name=game.current_player.name)
        return play_ai_turn(game, self.ai, self.human_player_idx, self.tracker)


def play_round_vs_ai(game: Game, ai: BasicAI, human_player_idx: int, tracker: GameTracker | None = None) -> None:
    """Play a complete round against AI."""
    game.deal()

    # Start hand tracking
    if tracker:
        tracker.start_hand(dealer_name=game.dealer.name)

    seats: list[Seat] = [CLIHumanSeat(human_player_idx, tracker), CLIAISeat(ai, human_player_idx, tracker)]
    if human_player_idx == 1:
        seats.reverse()
    outcome = run_round(game, seats)

    finish_round(game, outcome.ended_by, outcome.result, tracker)


def play_round_pvp(game: Game, tracker: GameTracker | None = None) -> None:
    """Play a complete round player vs player."""
    game.deal()

    # Start hand tracking
    if tracker:
        tracker.start_hand(dealer_name=game.dealer.name)

    seats = [CLIHumanSeat(idx, tracker, pause_before_turn=True) for idx in range(2)]
    outcome = run_round(game, seats)

    finish_round(game, outcome.ended_by, outcome.result, tracker)
