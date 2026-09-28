"""AI vs AI game simulator with metrics collection."""

import argparse
import logging
import random
import sys
import time
from dataclasses import dataclass, field

from gin_rummy.ai import BasicAI, ContextAwareAI, DrawChoice, MonteCarloAI, StatisticalAI
from gin_rummy.models import Card, Player
from gin_rummy.config import Config
from gin_rummy.game import Game, GamePhase, RoundResult
from gin_rummy.game_runner import (
    TurnResult,
    TurnActions,
    execute_ai_turn,
)

# Lazy import for LearningAI to avoid requiring torch
_LearningAI = None


def _get_learning_ai():
    """Lazy import LearningAI to avoid torch dependency."""
    global _LearningAI
    if _LearningAI is None:
        from gin_rummy.learning import LearningAI

        _LearningAI = LearningAI
    return _LearningAI


logger = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    """Format seconds as Xm Ys."""
    mins = int(seconds) // 60
    secs = seconds - mins * 60
    if mins > 0:
        return f"{mins}m {secs:.1f}s"
    return f"{secs:.1f}s"


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


@dataclass
class GameResult:
    """Result of a single game for progress reporting."""

    winner_idx: int | None = None
    rounds: int = 0
    hands_won_p1: int = 0
    hands_won_p2: int = 0
    score_p1: int = 0
    score_p2: int = 0
    ai1_turn_time: float = 0.0
    ai1_turns: int = 0
    ai2_turn_time: float = 0.0
    ai2_turns: int = 0

    @property
    def ai1_avg_turn(self) -> float:
        return self.ai1_turn_time / self.ai1_turns if self.ai1_turns > 0 else 0.0

    @property
    def ai2_avg_turn(self) -> float:
        return self.ai2_turn_time / self.ai2_turns if self.ai2_turns > 0 else 0.0


@dataclass
class PlayerMetrics:
    """Metrics for a single player."""

    games_won: int = 0
    rounds_won: int = 0
    total_points: int = 0
    gins: int = 0
    undercuts_made: int = 0
    undercuts_received: int = 0
    knocks: int = 0
    total_knock_deadwood: int = 0
    draws_from_deck: int = 0
    draws_from_discard: int = 0

    # Points breakdown
    points_from_gins: int = 0
    points_from_knocks: int = 0  # Regular knock wins (not gin)
    points_from_undercuts: int = 0

    @property
    def avg_knock_deadwood(self) -> float:
        """Average deadwood when knocking."""
        return self.total_knock_deadwood / self.knocks if self.knocks > 0 else 0.0

    @property
    def discard_draw_rate(self) -> float:
        """Percentage of draws from discard pile."""
        total = self.draws_from_deck + self.draws_from_discard
        return self.draws_from_discard / total if total > 0 else 0.0

    @property
    def knock_wins(self) -> int:
        """Number of rounds won by knocking (gin + regular knock)."""
        return self.gins + (self.rounds_won - self.gins - self.undercuts_made)

    @property
    def points_per_knock_win(self) -> float:
        """Average points scored when winning by knock (gin or regular)."""
        knock_points = self.points_from_gins + self.points_from_knocks
        knock_wins = self.rounds_won - self.undercuts_made
        return knock_points / knock_wins if knock_wins > 0 else 0.0

    @property
    def points_per_undercut(self) -> float:
        """Average points scored per undercut."""
        return self.points_from_undercuts / self.undercuts_made if self.undercuts_made > 0 else 0.0


@dataclass
class SimulatorMetrics:
    """Aggregated metrics from simulation runs."""

    player1_name: str = "Player 1"
    player2_name: str = "Player 2"
    player1_ai_class: str = "BasicAI"
    player2_ai_class: str = "BasicAI"
    player1: PlayerMetrics = field(default_factory=PlayerMetrics)
    player2: PlayerMetrics = field(default_factory=PlayerMetrics)
    games_played: int = 0
    rounds_played: int = 0
    draws: int = 0

    # Round ending breakdown
    rounds_ended_by_gin: int = 0
    rounds_ended_by_undercut: int = 0
    rounds_ended_by_knock: int = 0  # Regular knock (not gin, knocker won)

    def get_player_metrics(self, player_idx: int) -> PlayerMetrics:
        """Get metrics for a player by index."""
        return self.player1 if player_idx == 0 else self.player2

    def summary(self) -> str:
        """Return a formatted summary of the metrics."""
        # Build column headers with AI class names
        p1_header = f"{self.player1_name} ({self.player1_ai_class})"
        p2_header = f"{self.player2_name} ({self.player2_ai_class})"
        col_width = max(len(p1_header), len(p2_header), 12)
        line_width = 32 + col_width * 2 + 2

        # Calculate round ending percentages
        total = self.rounds_played if self.rounds_played > 0 else 1
        knock_pct = self.rounds_ended_by_knock / total * 100
        gin_pct = self.rounds_ended_by_gin / total * 100
        undercut_pct = self.rounds_ended_by_undercut / total * 100
        draw_pct = self.draws / total * 100

        lines = [
            "=" * line_width,
            "SIMULATION RESULTS",
            "=" * line_width,
            f"Games played: {self.games_played}",
            f"Total rounds: {self.rounds_played}",
            "",
            "Round Endings:",
            f"  Knock (regular):  {self.rounds_ended_by_knock:>5} ({knock_pct:5.1f}%)",
            f"  Gin:              {self.rounds_ended_by_gin:>5} ({gin_pct:5.1f}%)",
            f"  Undercut:         {self.rounds_ended_by_undercut:>5} ({undercut_pct:5.1f}%)",
            f"  Draw (exhausted): {self.draws:>5} ({draw_pct:5.1f}%)",
            "",
            f"{'Metric':<30} {p1_header:>{col_width}} {p2_header:>{col_width}}",
            "-" * line_width,
            f"{'Games won':<30} {self.player1.games_won:>{col_width}} {self.player2.games_won:>{col_width}}",
            f"{'Rounds won':<30} {self.player1.rounds_won:>{col_width}} {self.player2.rounds_won:>{col_width}}",
            f"{'Total points':<30} {self.player1.total_points:>{col_width}} {self.player2.total_points:>{col_width}}",
            f"{'Gins':<30} {self.player1.gins:>{col_width}} {self.player2.gins:>{col_width}}",
            f"{'Knocks':<30} {self.player1.knocks:>{col_width}} {self.player2.knocks:>{col_width}}",
            f"{'Avg knock deadwood':<30} {self.player1.avg_knock_deadwood:>{col_width}.1f} "
            f"{self.player2.avg_knock_deadwood:>{col_width}.1f}",
            f"{'Pts per knock win':<30} {self.player1.points_per_knock_win:>{col_width}.1f} "
            f"{self.player2.points_per_knock_win:>{col_width}.1f}",
            f"{'Undercuts made':<30} {self.player1.undercuts_made:>{col_width}} "
            f"{self.player2.undercuts_made:>{col_width}}",
            f"{'Pts per undercut':<30} {self.player1.points_per_undercut:>{col_width}.1f} "
            f"{self.player2.points_per_undercut:>{col_width}.1f}",
            f"{'Undercuts received':<30} {self.player1.undercuts_received:>{col_width}} "
            f"{self.player2.undercuts_received:>{col_width}}",
            f"{'Draws from deck':<30} {self.player1.draws_from_deck:>{col_width}} "
            f"{self.player2.draws_from_deck:>{col_width}}",
            f"{'Draws from discard':<30} {self.player1.draws_from_discard:>{col_width}} "
            f"{self.player2.draws_from_discard:>{col_width}}",
            f"{'Discard draw rate':<30} {self.player1.discard_draw_rate:>{col_width - 1}.1%} "
            f"{self.player2.discard_draw_rate:>{col_width - 1}.1%}",
            "=" * line_width,
        ]
        return "\n".join(lines)


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

        # Reset AI tracking for new hand (ContextAwareAI and LearningAI)
        for ai in (self.ai1, self.ai2):
            if hasattr(ai, "reset_for_new_hand"):
                ai.reset_for_new_hand()

        # First discard by non-dealer
        non_dealer_idx = 1 - game.dealer_idx
        ai = self.ai1 if non_dealer_idx == 0 else self.ai2
        discard = ai.decide_discard(game.current_player.hand)
        game.discard_to_start(discard)

        # Record first discard for opponent tracking
        other_ai = self.ai2 if non_dealer_idx == 0 else self.ai1
        if hasattr(other_ai, "record_opponent_discard"):
            other_ai.record_opponent_discard(discard)

        # Main game loop
        while game.phase == GamePhase.DRAWING:
            result = self._play_turn(game, game_result)
            if result is not None:
                return result

        return game.get_draw_result()

    def _play_turn(self, game: Game, game_result: GameResult) -> RoundResult | None:
        """Play a single turn using shared game runner logic.

        Returns RoundResult if round ended, None if round continues.
        """
        current_idx = game.current_player_idx
        ai = self.ai1 if current_idx == 0 else self.ai2
        other_ai = self.ai2 if current_idx == 0 else self.ai1
        player_metrics = self.metrics.get_player_metrics(current_idx)

        # Create callbacks for metrics tracking
        callbacks = SimulatorTurnCallbacks(player_metrics)

        # Execute the turn with timing
        turn_start = time.time()
        turn_result, _, round_result = execute_ai_turn(game, ai, other_ai, callbacks)
        turn_elapsed = time.time() - turn_start

        # Track per-AI timing
        if current_idx == 0:
            game_result.ai1_turn_time += turn_elapsed
            game_result.ai1_turns += 1
        else:
            game_result.ai2_turn_time += turn_elapsed
            game_result.ai2_turns += 1

        # Map TurnResult to RoundResult | None
        if turn_result == TurnResult.KNOCKED:
            # Round ended with knock - return the result from knock
            return round_result
        elif turn_result == TurnResult.DRAW:
            # Deck exhausted
            return game.get_draw_result()
        else:
            # Round continues
            return None

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


def create_ai(
    ai_type: str,
    config_path: str | None,
    model_path: str | None = None,
    stats_path: str | None = None,
) -> BasicAI:
    """Create an AI with optional config override.

    Args:
        ai_type: Type of AI ("basic", "context", "learning", or "statistical").
        config_path: Optional path to config override file.
        model_path: Path to trained model (for "learning" type only).
        stats_path: Path to stats file (for "statistical" type only).

    Returns:
        BasicAI, ContextAwareAI, StatisticalAI, or LearningAI instance.
    """
    config = None
    if config_path:
        config = Config.with_overrides(config_path)

    if ai_type == "learning":
        LearningAI = _get_learning_ai()
        return LearningAI(model_path=model_path, config=config)
    elif ai_type == "montecarlo":
        return MonteCarloAI(config)
    elif ai_type == "context":
        return ContextAwareAI(config)
    elif ai_type == "statistical":
        return StatisticalAI(stats_path=stats_path, config=config)
    else:
        return BasicAI(config)


def main() -> None:
    """CLI entry point for the simulator."""
    parser = argparse.ArgumentParser(
        description="Run AI vs AI Gin Rummy simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--num-games",
        type=int,
        default=100,
        help="Number of games to simulate",
    )
    parser.add_argument(
        "-t",
        "--target-score",
        type=int,
        default=100,
        help="Score needed to win a game (0 for single-round mode)",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=50,
        help="Maximum rounds per game (safety limit)",
    )
    parser.add_argument(
        "--ai1-type",
        type=str,
        choices=["basic", "context", "learning", "statistical", "montecarlo"],
        default="context",
        help="AI type for player 1",
    )
    parser.add_argument(
        "--ai2-type",
        type=str,
        choices=["basic", "context", "learning", "statistical", "montecarlo"],
        default="basic",
        help="AI type for player 2",
    )
    parser.add_argument(
        "--stats-file",
        type=str,
        default="models/statistical_ai.json",
        help="Path to stats file for Statistical AI (default: models/statistical_ai.json)",
    )
    parser.add_argument(
        "--ai1-config",
        type=str,
        default=None,
        help="Override config file for AI player 1",
    )
    parser.add_argument(
        "--ai2-config",
        type=str,
        default=None,
        help="Override config file for AI player 2",
    )
    parser.add_argument(
        "--ai1-model",
        type=str,
        default=None,
        help="Path to trained model for AI 1 (when --ai1-type=learning)",
    )
    parser.add_argument(
        "--ai2-model",
        type=str,
        default=None,
        help="Path to trained model for AI 2 (when --ai2-type=learning)",
    )

    args = parser.parse_args()

    # Configure logging based on verbosity
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose >= 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(name)s - %(levelname)s - %(message)s",
    )

    # Create AIs with optional config overrides
    ai1 = create_ai(args.ai1_type, args.ai1_config, args.ai1_model, args.stats_file)
    ai2 = create_ai(args.ai2_type, args.ai2_config, args.ai2_model, args.stats_file)

    config = SimulatorConfig(
        num_games=args.num_games,
        target_score=args.target_score,
        max_rounds_per_game=args.max_rounds,
        seed=args.seed,
    )

    # Show config info if overrides were used
    if args.ai1_config or args.ai2_config:
        print(f"AI 1: {args.ai1_type} (config: {args.ai1_config or 'default'})")
        print(f"AI 2: {args.ai2_type} (config: {args.ai2_config or 'default'})")
        print()

    simulator = Simulator(ai1=ai1, ai2=ai2, config=config)
    metrics = simulator.run(show_progress=True)

    # Save StatisticalAI stats after simulation
    for ai in [ai1, ai2]:
        if hasattr(ai, "save"):
            ai.save()
            if hasattr(ai, "get_stats_summary"):
                summary = ai.get_stats_summary()
                if summary.get("total_discard_samples", 0) > 0:
                    print(f"\nStatisticalAI stats: {summary['total_discard_samples']} samples collected")

    print(metrics.summary())


if __name__ == "__main__":
    main()
