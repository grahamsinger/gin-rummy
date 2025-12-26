"""AI vs AI game simulator with metrics collection."""

import argparse
import logging
import random
from dataclasses import dataclass, field

from gin_rummy.ai import BasicAI, ContextAwareAI, DrawChoice
from gin_rummy.card import Card
from gin_rummy.config import Config
from gin_rummy.game import Game, GamePhase, RoundResult
from gin_rummy.game_runner import (
    TurnResult,
    TurnActions,
    TurnCallbacks,
    execute_ai_turn,
)
from gin_rummy.player import Player


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

    @property
    def avg_knock_deadwood(self) -> float:
        """Average deadwood when knocking."""
        return self.total_knock_deadwood / self.knocks if self.knocks > 0 else 0.0

    @property
    def discard_draw_rate(self) -> float:
        """Percentage of draws from discard pile."""
        total = self.draws_from_deck + self.draws_from_discard
        return self.draws_from_discard / total if total > 0 else 0.0


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

    def get_player_metrics(self, player_idx: int) -> PlayerMetrics:
        """Get metrics for a player by index."""
        return self.player1 if player_idx == 0 else self.player2

    def summary(self) -> str:
        """Return a formatted summary of the metrics."""
        # Build column headers with AI class names
        p1_header = f"{self.player1_name} ({self.player1_ai_class})"
        p2_header = f"{self.player2_name} ({self.player2_ai_class})"
        col_width = max(len(p1_header), len(p2_header), 12)

        lines = [
            "=" * (32 + col_width * 2 + 2),
            "SIMULATION RESULTS",
            "=" * (32 + col_width * 2 + 2),
            f"Games played: {self.games_played}",
            f"Total rounds: {self.rounds_played}",
            f"Draws (deck exhausted): {self.draws}",
            "",
            f"{'Metric':<30} {p1_header:>{col_width}} {p2_header:>{col_width}}",
            "-" * (32 + col_width * 2 + 2),
            f"{'Games won':<30} {self.player1.games_won:>{col_width}} {self.player2.games_won:>{col_width}}",
            f"{'Rounds won':<30} {self.player1.rounds_won:>{col_width}} {self.player2.rounds_won:>{col_width}}",
            f"{'Total points':<30} {self.player1.total_points:>{col_width}} {self.player2.total_points:>{col_width}}",
            f"{'Gins':<30} {self.player1.gins:>{col_width}} {self.player2.gins:>{col_width}}",
            f"{'Knocks':<30} {self.player1.knocks:>{col_width}} {self.player2.knocks:>{col_width}}",
            f"{'Avg knock deadwood':<30} {self.player1.avg_knock_deadwood:>{col_width}.1f} {self.player2.avg_knock_deadwood:>{col_width}.1f}",
            f"{'Undercuts made':<30} {self.player1.undercuts_made:>{col_width}} {self.player2.undercuts_made:>{col_width}}",
            f"{'Undercuts received':<30} {self.player1.undercuts_received:>{col_width}} {self.player2.undercuts_received:>{col_width}}",
            f"{'Draws from deck':<30} {self.player1.draws_from_deck:>{col_width}} {self.player2.draws_from_deck:>{col_width}}",
            f"{'Draws from discard':<30} {self.player1.draws_from_discard:>{col_width}} {self.player2.draws_from_discard:>{col_width}}",
            f"{'Discard draw rate':<30} {self.player1.discard_draw_rate:>{col_width - 1}.1%} {self.player2.discard_draw_rate:>{col_width - 1}.1%}",
            "=" * (32 + col_width * 2 + 2),
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

    def on_knock(self, player: Player, discard: Card, deadwood: int) -> None:
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

    def run(self) -> SimulatorMetrics:
        """Run the simulation and return metrics."""
        if self.config.seed is not None:
            random.seed(self.config.seed)

        self.metrics = SimulatorMetrics(
            player1_name="AI 1",
            player2_name="AI 2",
            player1_ai_class=type(self.ai1).__name__,
            player2_ai_class=type(self.ai2).__name__,
        )

        for game_num in range(self.config.num_games):
            logger.info("=== Game %d ===", game_num + 1)
            self._run_game()
            self.metrics.games_played += 1

        return self.metrics

    def _run_game(self) -> None:
        """Run a single game until someone reaches target score."""
        game = Game("AI 1", "AI 2")
        round_num = 0

        while round_num < self.config.max_rounds_per_game:
            round_num += 1
            logger.info("--- Round %d ---", round_num)

            result = self._run_round(game)
            self.metrics.rounds_played += 1

            if result.is_draw:
                self.metrics.draws += 1
            else:
                self._record_round_result(game, result)

            # Check for game winner
            if self.config.target_score > 0:
                for idx, player in enumerate(game.players):
                    if player.score >= self.config.target_score:
                        self.metrics.get_player_metrics(idx).games_won += 1
                        logger.info(
                            "Game won by %s with score %d",
                            player.name,
                            player.score,
                        )
                        return

            game.new_round()

        logger.warning("Game ended due to max rounds limit (%d)", round_num)

    def _run_round(self, game: Game) -> RoundResult:
        """Run a single round and return the result."""
        game.deal()

        # Reset ContextAwareAI tracking for new hand
        for ai in (self.ai1, self.ai2):
            if isinstance(ai, ContextAwareAI):
                ai.reset_for_new_hand()

        # First discard by non-dealer
        non_dealer_idx = 1 - game.dealer_idx
        ai = self.ai1 if non_dealer_idx == 0 else self.ai2
        discard = ai.decide_discard(game.current_player.hand)
        game.discard_to_start(discard)

        # Record first discard for opponent tracking
        other_ai = self.ai2 if non_dealer_idx == 0 else self.ai1
        if isinstance(other_ai, ContextAwareAI):
            other_ai.record_opponent_discard(discard)

        # Main game loop
        while game.phase == GamePhase.DRAWING:
            result = self._play_turn(game)
            if result is not None:
                return result

        return game.get_draw_result()

    def _play_turn(self, game: Game) -> RoundResult | None:
        """Play a single turn using shared game runner logic.

        Returns RoundResult if round ended, None if round continues.
        """
        current_idx = game.current_player_idx
        ai = self.ai1 if current_idx == 0 else self.ai2
        other_ai = self.ai2 if current_idx == 0 else self.ai1
        player_metrics = self.metrics.get_player_metrics(current_idx)

        # Create callbacks for metrics tracking
        callbacks = SimulatorTurnCallbacks(player_metrics)

        # Execute the turn using shared game logic
        turn_result, _, round_result = execute_ai_turn(game, ai, other_ai, callbacks)

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

        if result.is_undercut:
            winner_metrics.undercuts_made += 1
            loser_metrics.undercuts_received += 1


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


def create_ai(ai_type: str, config_path: str | None) -> BasicAI:
    """Create an AI with optional config override.

    Args:
        ai_type: Type of AI ("basic" or "context").
        config_path: Optional path to config override file.

    Returns:
        BasicAI or ContextAwareAI instance.
    """
    config = None
    if config_path:
        config = Config.with_overrides(config_path)

    if ai_type == "context":
        return ContextAwareAI(config)
    else:
        return BasicAI(config)


def main() -> None:
    """CLI entry point for the simulator."""
    parser = argparse.ArgumentParser(
        description="Run AI vs AI Gin Rummy simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-n", "--num-games",
        type=int,
        default=100,
        help="Number of games to simulate",
    )
    parser.add_argument(
        "-t", "--target-score",
        type=int,
        default=100,
        help="Score needed to win a game (0 for single-round mode)",
    )
    parser.add_argument(
        "-s", "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "-v", "--verbose",
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
        choices=["basic", "context"],
        default="context",
        help="AI type for player 1",
    )
    parser.add_argument(
        "--ai2-type",
        type=str,
        choices=["basic", "context"],
        default="basic",
        help="AI type for player 2",
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
    ai1 = create_ai(args.ai1_type, args.ai1_config)
    ai2 = create_ai(args.ai2_type, args.ai2_config)

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
    metrics = simulator.run()
    print(metrics.summary())


if __name__ == "__main__":
    main()
