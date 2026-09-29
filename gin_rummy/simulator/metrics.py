"""Simulation results: per-game, per-player and overall metrics, and their summary."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _format_time(seconds: float) -> str:
    """Format seconds as Xm Ys."""
    mins = int(seconds) // 60
    secs = seconds - mins * 60
    if mins > 0:
        return f"{mins}m {secs:.1f}s"
    return f"{secs:.1f}s"


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
