"""AI vs AI game simulator with metrics collection."""

import argparse
import logging
import random
from dataclasses import dataclass, field

from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.game import Game, GamePhase, InvalidActionError, RoundResult


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
        lines = [
            "=" * 60,
            "SIMULATION RESULTS",
            "=" * 60,
            f"Games played: {self.games_played}",
            f"Total rounds: {self.rounds_played}",
            f"Draws (deck exhausted): {self.draws}",
            "",
            f"{'Metric':<30} {self.player1_name:>12} {self.player2_name:>12}",
            "-" * 60,
            f"{'Games won':<30} {self.player1.games_won:>12} {self.player2.games_won:>12}",
            f"{'Rounds won':<30} {self.player1.rounds_won:>12} {self.player2.rounds_won:>12}",
            f"{'Total points':<30} {self.player1.total_points:>12} {self.player2.total_points:>12}",
            f"{'Gins':<30} {self.player1.gins:>12} {self.player2.gins:>12}",
            f"{'Knocks':<30} {self.player1.knocks:>12} {self.player2.knocks:>12}",
            f"{'Avg knock deadwood':<30} {self.player1.avg_knock_deadwood:>12.1f} {self.player2.avg_knock_deadwood:>12.1f}",
            f"{'Undercuts made':<30} {self.player1.undercuts_made:>12} {self.player2.undercuts_made:>12}",
            f"{'Undercuts received':<30} {self.player1.undercuts_received:>12} {self.player2.undercuts_received:>12}",
            f"{'Draws from deck':<30} {self.player1.draws_from_deck:>12} {self.player2.draws_from_deck:>12}",
            f"{'Draws from discard':<30} {self.player1.draws_from_discard:>12} {self.player2.draws_from_discard:>12}",
            f"{'Discard draw rate':<30} {self.player1.discard_draw_rate:>11.1%} {self.player2.discard_draw_rate:>11.1%}",
            "=" * 60,
        ]
        return "\n".join(lines)


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

        # First discard by non-dealer
        non_dealer_idx = 1 - game.dealer_idx
        ai = self.ai1 if non_dealer_idx == 0 else self.ai2
        discard = ai.decide_discard(game.current_player.hand)
        game.discard_to_start(discard)

        # Main game loop
        while game.phase == GamePhase.DRAWING:
            result = self._play_turn(game)
            if result is not None:
                return result

        return game.get_draw_result()

    def _play_turn(self, game: Game) -> RoundResult | None:
        """Play a single turn. Returns RoundResult if round ended."""
        current_idx = game.current_player_idx
        ai = self.ai1 if current_idx == 0 else self.ai2
        player_metrics = self.metrics.get_player_metrics(current_idx)
        current = game.current_player

        # Draw phase
        draw_choice = ai.decide_draw(current.hand, game.top_of_discard)

        if draw_choice == DrawChoice.DISCARD and game.top_of_discard:
            card = game.draw_from_discard()
            player_metrics.draws_from_discard += 1
        else:
            try:
                card = game.draw_from_deck()
                player_metrics.draws_from_deck += 1
            except InvalidActionError:
                # Deck exhausted
                return game.get_draw_result()

        # Discard/knock phase
        discard, should_knock = ai.make_turn_decision(
            current.hand, game.top_of_discard, card
        )

        if should_knock and game.can_knock:
            # Calculate post-discard deadwood for metrics
            from gin_rummy.melds import analyze_hand

            test_cards = [c for c in current.hand if c != discard]
            post_discard_deadwood = analyze_hand(test_cards).deadwood_value
            player_metrics.total_knock_deadwood += post_discard_deadwood
            player_metrics.knocks += 1

            # knock() expects to be called during DISCARDING phase (before discard)
            result = game.knock()
            return result
        else:
            game.discard(discard)
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

    config = SimulatorConfig(
        num_games=args.num_games,
        target_score=args.target_score,
        max_rounds_per_game=args.max_rounds,
        seed=args.seed,
    )

    simulator = Simulator(config=config)
    metrics = simulator.run()
    print(metrics.summary())


if __name__ == "__main__":
    main()
