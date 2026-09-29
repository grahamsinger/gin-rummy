"""The simulator: seeded AI vs AI games over the round runner."""

import logging
import random
import sys
import time
from dataclasses import dataclass

from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.game import Game, RoundResult
from gin_rummy.game_runner import TurnActions, TurnResult
from gin_rummy.models import Card, Player
from gin_rummy.round_runner import AISeat, run_round
from gin_rummy.simulator.metrics import GameResult, PlayerMetrics, SimulatorMetrics, _format_time

logger = logging.getLogger(__name__)


@dataclass
class SimulatorConfig:
    """Configuration for the simulator.

    Attributes:
        num_games: Number of complete games to simulate.
        target_score: Score needed to win a game (0 = play forever / single round mode).
        max_rounds_per_game: Safety limit to prevent infinite games.
        seed: Random seed for reproducibility (None = random).
    """

    num_games: int = 100
    target_score: int = 100
    max_rounds_per_game: int = 50
    seed: int | None = None


class SimulatorTurnCallbacks:
    """Callbacks for AI turn side effects in Simulator mode.

    Handles metrics tracking (draw counts, knock statistics).
    """

    def __init__(self, player_metrics: PlayerMetrics) -> None:
        self.player_metrics = player_metrics

    def on_draw(self, player: Player, source: DrawChoice, card: Card) -> None:
        """Track draw source."""
        if source == DrawChoice.DISCARD:
            self.player_metrics.draws_from_discard += 1
        else:
            self.player_metrics.draws_from_deck += 1

    def on_discard(self, player: Player, card: Card) -> None:
        """No-op for discard in simulator."""
        pass

    def on_knock(self, player: Player, discard: Card, deadwood: int, result: RoundResult) -> None:
        """Track knock statistics."""
        self.player_metrics.knocks += 1
        self.player_metrics.total_knock_deadwood += deadwood

    def on_turn_complete(self, player: Player, actions: TurnActions) -> None:
        """No-op - metrics already tracked in other callbacks."""
        pass


class _TimedSeat(AISeat):
    """AI seat that records metrics and how long its turns took."""

    def __init__(self, ai: BasicAI, player_metrics: PlayerMetrics) -> None:
        super().__init__(ai, SimulatorTurnCallbacks(player_metrics))
        self.turn_time = 0.0
        self.turns = 0

    def play_turn(self, game: Game) -> tuple[TurnResult, TurnActions | None, RoundResult | None]:
        turn_start = time.time()
        outcome = super().play_turn(game)
        self.turn_time += time.time() - turn_start
        self.turns += 1
        return outcome


class Simulator:
    """Runs AI vs AI games and collects metrics."""

    def __init__(
        self,
        ai1: BasicAI | None = None,
        ai2: BasicAI | None = None,
        config: SimulatorConfig | None = None,
    ) -> None:
        """Initialize the simulator.

        Args:
            ai1: AI for player 1 (default: BasicAI).
            ai2: AI for player 2 (default: BasicAI).
            config: Simulator configuration (default: SimulatorConfig()).
        """
        self.ai1 = ai1 or BasicAI()
        self.ai2 = ai2 or BasicAI()
        self.config = config or SimulatorConfig()
        self.metrics = SimulatorMetrics()

    def run(self, show_progress: bool = False) -> SimulatorMetrics:
        """Run the simulation and return metrics."""
        if self.config.seed is not None:
            random.seed(self.config.seed)

        self.metrics = SimulatorMetrics(
            player1_name="AI 1",
            player2_name="AI 2",
            player1_ai_class=type(self.ai1).__name__,
            player2_ai_class=type(self.ai2).__name__,
        )

        start_time = time.time()

        for game_num in range(self.config.num_games):
            logger.info("=== Game %d ===", game_num + 1)
            game_result = self._run_game()
            self.metrics.games_played += 1

            if show_progress:
                elapsed = time.time() - start_time
                p1_wins = self.metrics.player1.games_won
                p2_wins = self.metrics.player2.games_won
                game_time = game_result.ai1_turn_time + game_result.ai2_turn_time
                sys.stderr.write(
                    f"Game {game_num + 1}/{self.config.num_games} "
                    f"| Wins: {p1_wins}-{p2_wins} "
                    f"| Score: {game_result.score_p1}-{game_result.score_p2} "
                    f"| {game_result.rounds} hands ({game_result.hands_won_p1}-{game_result.hands_won_p2}), "
                    f"{game_result.ai1_turns + game_result.ai2_turns} turns "
                    f"| {_format_time(game_time)} "
                    f"({game_result.ai1_avg_turn:.2f}s, "
                    f"{game_result.ai2_avg_turn:.2f}s/turn) "
                    f"| Total: {_format_time(elapsed)}\n"
                )
                sys.stderr.flush()

        if show_progress:
            total_time = time.time() - start_time
            sys.stderr.write(f"Completed {self.config.num_games} games in {_format_time(total_time)}\n")
            sys.stderr.flush()

        return self.metrics

    def _run_game(self) -> GameResult:
        """Run a single game until someone reaches target score."""
        game = Game("AI 1", "AI 2")
        round_num = 0
        game_result = GameResult()

        while round_num < self.config.max_rounds_per_game:
            round_num += 1
            logger.info("--- Round %d ---", round_num)

            result = self._run_round(game, game_result)
            self.metrics.rounds_played += 1

            if result.is_draw:
                self.metrics.draws += 1
            else:
                self._record_round_result(game, result)
                if result.winner is not None:
                    winner_idx = 0 if result.winner == game.players[0] else 1
                    if winner_idx == 0:
                        game_result.hands_won_p1 += 1
                    else:
                        game_result.hands_won_p2 += 1

            # Check for game winner
            if self.config.target_score > 0:
                for idx, player in enumerate(game.players):
                    if player.score >= self.config.target_score:
                        self.metrics.get_player_metrics(idx).games_won += 1
                        game_result.winner_idx = idx
                        game_result.rounds = round_num
                        game_result.score_p1 = game.players[0].score
                        game_result.score_p2 = game.players[1].score
                        logger.info(
                            "Game won by %s with score %d",
                            player.name,
                            player.score,
                        )
                        return game_result

            game.new_round()

        logger.warning("Game ended due to max rounds limit (%d)", round_num)
        game_result.rounds = round_num
        game_result.score_p1 = game.players[0].score
        game_result.score_p2 = game.players[1].score
        return game_result

    def _run_round(self, game: Game, game_result: GameResult) -> RoundResult:
        """Run a single round and return the result."""
        game.deal()
        seats = [
            _TimedSeat(self.ai1, self.metrics.get_player_metrics(0)),
            _TimedSeat(self.ai2, self.metrics.get_player_metrics(1)),
        ]
        outcome = run_round(game, seats)

        game_result.ai1_turn_time += seats[0].turn_time
        game_result.ai1_turns += seats[0].turns
        game_result.ai2_turn_time += seats[1].turn_time
        game_result.ai2_turns += seats[1].turns

        assert outcome.result is not None  # no stop_when, so the round ran to its end
        return outcome.result

    def _record_round_result(self, game: Game, result: RoundResult) -> None:
        """Record metrics from a round result."""
        if result.winner is None:
            return

        winner_idx = 0 if result.winner == game.players[0] else 1
        loser_idx = 1 - winner_idx
        winner_metrics = self.metrics.get_player_metrics(winner_idx)
        loser_metrics = self.metrics.get_player_metrics(loser_idx)

        winner_metrics.rounds_won += 1
        winner_metrics.total_points += result.points

        if result.is_gin:
            winner_metrics.gins += 1
            winner_metrics.points_from_gins += result.points
            self.metrics.rounds_ended_by_gin += 1
        elif result.is_undercut:
            winner_metrics.undercuts_made += 1
            winner_metrics.points_from_undercuts += result.points
            loser_metrics.undercuts_received += 1
            self.metrics.rounds_ended_by_undercut += 1
        else:
            # Regular knock (knocker won, not gin)
            winner_metrics.points_from_knocks += result.points
            self.metrics.rounds_ended_by_knock += 1

        # Update StatisticalAI learning
        for idx, ai in enumerate([self.ai1, self.ai2]):
            if hasattr(ai, "record_round_outcome"):
                won = idx == winner_idx
                points = result.points if won else -result.points
                ai.record_round_outcome(won, points)


def run_simulation(
    num_games: int = 100,
    target_score: int = 100,
    seed: int | None = None,
    ai1: BasicAI | None = None,
    ai2: BasicAI | None = None,
) -> SimulatorMetrics:
    """Convenience function to run a simulation.

    Args:
        num_games: Number of games to simulate.
        target_score: Score needed to win a game.
        seed: Random seed for reproducibility.
        ai1: AI for player 1.
        ai2: AI for player 2.

    Returns:
        SimulatorMetrics with results.
    """
    config = SimulatorConfig(
        num_games=num_games,
        target_score=target_score,
        seed=seed,
    )
    simulator = Simulator(ai1=ai1, ai2=ai2, config=config)
    return simulator.run()
