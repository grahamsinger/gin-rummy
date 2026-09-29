"""Statistical AI that learns from experience."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.types import DiscardReasoning, DrawChoice, DrawReasoning, KnockReasoning
from gin_rummy.config import Config
from gin_rummy.models import Card, Hand, analyze_hand
from gin_rummy.models.game_context import GameContext

logger = logging.getLogger(__name__)


def _deadwood_bucket(deadwood: int) -> str:
    """Get deadwood bucket for draw statistics."""
    if deadwood <= 10:
        return "0-10"
    elif deadwood <= 20:
        return "11-20"
    elif deadwood <= 30:
        return "21-30"
    else:
        return "31+"


class StatisticalAI(BasicAI):
    """AI that learns from experience by tracking action outcomes.

    Tracks statistics for:
    - Card discards: which cards lead to wins/losses
    - Draw decisions: when drawing from discard helps
    - Knock decisions: optimal deadwood threshold for knocking

    Statistics persist to a JSON file and improve over many games.
    Falls back to BasicAI logic when insufficient data exists.
    """

    # Minimum samples before using statistical decision
    MIN_SAMPLES = 20

    def __init__(
        self,
        stats_path: Path | str | None = None,
        config: Config | None = None,
    ) -> None:
        """Initialize Statistical AI.

        Args:
            stats_path: Path to JSON file for persisting statistics.
            config: Optional config override.
        """
        super().__init__(config)

        if stats_path is not None:
            self.stats_path = Path(stats_path)
        else:
            self.stats_path = None

        # Statistics storage
        # Card discard stats: card_index -> {times, wins, points}
        self.discard_stats: dict[int, dict[str, int]] = {}

        # Draw stats: bucket -> {deck_draws, deck_wins, discard_draws, discard_wins}
        self.draw_stats: dict[str, dict[str, int]] = {}

        # Knock stats: deadwood -> {knocked, knock_wins, continued, continue_wins}
        self.knock_stats: dict[int, dict[str, int]] = {}

        # Track decisions made this round (for updating after outcome)
        self._round_discards: list[int] = []  # card indices discarded
        self._round_draws: list[tuple[str, str]] = []  # (bucket, "deck"|"discard")
        self._round_knocks: list[tuple[int, bool]] = []  # (deadwood, did_knock)

        # Load existing stats
        if self.stats_path and self.stats_path.exists():
            self.load()

    def reset_for_new_hand(self) -> None:
        """Reset tracking for a new hand."""
        super().reset_for_new_hand()
        self._round_discards = []
        self._round_draws = []
        self._round_knocks = []

    # Each decision has one implementation (`_evaluate_stats_*`) that ALSO
    # RECORDS the sample for learning (_round_draws/_round_discards/
    # _round_knocks). The plain method returns its choice and the
    # *_with_reasoning twin describes the statistics it used. Call exactly one
    # of the pair per decision on a given instance: calling both would record
    # the sample twice (tests that compare them use a fresh instance per call).

    def decide_draw(self, hand: Hand, discard_top: Card | None, context: GameContext | None = None) -> DrawChoice:
        """Use statistics to decide draw, with BasicAI fallback."""
        return self._evaluate_stats_draw(hand, discard_top, context)[0]

    def decide_draw_with_reasoning(
        self, hand: Hand, discard_top: Card | None, context: GameContext | None = None
    ) -> DrawReasoning:
        choice, reasoning, factors = self._evaluate_stats_draw(hand, discard_top, context)
        return DrawReasoning(choice=choice, reasoning=reasoning, factors=factors)

    def _evaluate_stats_draw(
        self, hand: Hand, discard_top: Card | None, context: GameContext | None = None
    ) -> tuple[DrawChoice, str, list[str]]:
        if discard_top is None:
            return DrawChoice.DECK, "Drew from DECK: discard pile empty", []

        bucket = _deadwood_bucket(hand.deadwood_total)
        stats = self.draw_stats.get(bucket)
        samples = (stats.get("deck_draws", 0) + stats.get("discard_draws", 0)) if stats else 0
        factors = [f"Deadwood bucket: {bucket}"]

        if stats is None or samples < self.MIN_SAMPLES:
            # Fall back to BasicAI
            choice, _, reason = self._evaluate_draw(hand, discard_top, context)
            factors += [f"Samples: {samples} < {self.MIN_SAMPLES} (BasicAI fallback)", reason]
            where = f"{discard_top} from DISCARD" if choice == DrawChoice.DISCARD else "from DECK"
            reasoning = f"Drew {where}: too few samples, BasicAI fallback ({reason})"
        else:
            # Calculate win rates
            deck_draws = stats.get("deck_draws", 0)
            deck_wins = stats.get("deck_wins", 0)
            discard_draws = stats.get("discard_draws", 0)
            discard_wins = stats.get("discard_wins", 0)

            deck_rate = deck_wins / deck_draws if deck_draws > 0 else 0.5
            discard_rate = discard_wins / discard_draws if discard_draws > 0 else 0.5

            # Also check if the discard card itself would help (BasicAI logic)
            helps, _ = self._card_helps_hand(hand, discard_top)

            # Probabilistic selection based on win rates; halve the discard
            # probability when the card does not help the hand
            total_rate = deck_rate + discard_rate
            if helps:
                discard_prob = discard_rate / total_rate if total_rate > 0 else 0.5
            else:
                discard_prob = discard_rate / total_rate * 0.5 if total_rate > 0 else 0.25
            choice = DrawChoice.DISCARD if random.random() < discard_prob else DrawChoice.DECK

            logger.info(
                "Draw decision: %s (bucket=%s, deck_rate=%.2f, discard_rate=%.2f, helps=%s)",
                choice.name,
                bucket,
                deck_rate,
                discard_rate,
                helps,
            )
            factors += [
                f"Deck win rate: {deck_rate:.2f} ({deck_draws} draws)",
                f"Discard win rate: {discard_rate:.2f} ({discard_draws} draws)",
                f"{discard_top} helps hand: {helps}",
                f"P(discard) = {discard_prob:.2f}",
            ]
            where = f"{discard_top} from DISCARD" if choice == DrawChoice.DISCARD else "from DECK"
            reasoning = (
                f"Drew {where}: P(discard)={discard_prob:.2f} from win rates "
                f"(deck={deck_rate:.2f}, discard={discard_rate:.2f}, helps={helps})"
            )

        # Record decision for later update
        self._round_draws.append((bucket, "discard" if choice == DrawChoice.DISCARD else "deck"))
        return choice, reasoning, factors

    def decide_discard(self, hand: Hand, context: GameContext | None = None) -> Card:
        """Blend BasicAI's deadwood analysis with historical win rates."""
        return self._evaluate_stats_discard(hand)[0]

    def decide_discard_with_reasoning(self, hand: Hand, context: GameContext | None = None) -> DiscardReasoning:
        card, reasoning, factors, options = self._evaluate_stats_discard(hand)
        return DiscardReasoning(card=card, reasoning=reasoning, factors=factors, options_considered=options)

    def _evaluate_stats_discard(self, hand: Hand) -> tuple[Card, str, list[str], list[tuple[str, int]]]:
        cards = list(hand)
        best_discard = None
        best_score = float("-inf")
        options: list[tuple[Card, float, int, float]] = []

        for i, card in enumerate(cards):
            remaining = cards[:i] + cards[i + 1 :]
            deadwood = analyze_hand(remaining).deadwood_value

            # Base score: lower deadwood is better (negate so higher = better)
            base_score = -deadwood

            # Adjust by historical win rate for this card: cards with a HIGH
            # win rate when discarded are good discards (+/-10 point swing)
            card_stats = self.discard_stats.get(card.index)
            if card_stats and card_stats.get("times", 0) >= 10:
                win_rate = card_stats.get("wins", 0) / card_stats["times"]
                win_adjustment = (win_rate - 0.5) * 20
            else:
                win_rate = 0.5
                win_adjustment = 0

            score = base_score + win_adjustment
            options.append((card, score, deadwood, win_rate))
            if score > best_score:
                best_score = score
                best_discard = card

        # Fallback
        if best_discard is None:
            best_discard = max(cards, key=lambda c: c.deadwood_value)

        options.sort(key=lambda x: -x[1])
        logger.info(
            "Discard decision: %s (score=%.1f, top3=%s)",
            best_discard,
            best_score,
            [(str(c), f"dw={dw},wr={wr:.2f}") for c, _, dw, wr in options[:3]],
        )

        # Record for later update - but only for real discards, not
        # hypothetical evaluations from _card_helps_hand (those would
        # poison the learned win-rate statistics with phantom samples)
        if not self._in_hypothetical:
            self._round_discards.append(best_discard.index)

        chosen = next((o for o in options if o[0] == best_discard), None)
        if chosen is None:
            return best_discard, f"Discarded {best_discard}: fallback to highest deadwood value", [], []
        _, score, deadwood, win_rate = chosen
        factors = [
            f"Hand size: {len(cards)} cards",
            f"Resulting deadwood: {deadwood}",
            f"Historical win rate when discarded: {win_rate:.2f}",
            f"Stats-adjusted score: {score:.1f}",
        ]
        reasoning = f"Discarded {best_discard}: deadwood={deadwood}, win rate {win_rate:.2f} (score={score:.1f})"
        return best_discard, reasoning, factors, [(str(c), dw) for c, _, dw, _ in options[:5]]

    def should_knock(self, hand: Hand, context: GameContext | None = None, pending_discard: Card | None = None) -> bool:
        """Use statistics to decide whether to knock, with BasicAI fallback."""
        return self._evaluate_stats_knock(hand, context)[0]

    def should_knock_with_reasoning(
        self, hand: Hand, context: GameContext | None = None, pending_discard: Card | None = None
    ) -> KnockReasoning:
        decision, reasoning, factors = self._evaluate_stats_knock(hand, context)
        return KnockReasoning(should_knock=decision, reasoning=reasoning, score=None, factors=factors)

    def _evaluate_stats_knock(self, hand: Hand, context: GameContext | None) -> tuple[bool, str, list[str]]:
        deadwood = hand.deadwood_total
        factors = [f"Deadwood: {deadwood}"]

        # Always knock with gin
        if deadwood == 0:
            self._round_knocks.append((0, True))
            return True, "Knocked: GIN! (deadwood=0)", factors + ["GIN achieved!"]

        # Can't knock if deadwood over threshold
        threshold = self._knock_threshold_for(context)
        if deadwood > threshold:
            return (
                False,
                f"No knock: deadwood={deadwood} > {threshold}",
                factors + [f"Cannot knock: deadwood > {threshold}"],
            )

        stats = self.knock_stats.get(deadwood)
        samples = (stats.get("knocked", 0) + stats.get("continued", 0)) if stats else 0

        if stats is None or samples < self.MIN_SAMPLES:
            # Fall back to BasicAI
            basic = super().should_knock_with_reasoning(hand, context)
            decision = basic.should_knock
            factors = basic.factors + [f"Samples: {samples} < {self.MIN_SAMPLES} (BasicAI fallback)"]
            reasoning = f"{basic.reasoning} [too few samples, BasicAI fallback]"
        else:
            knocked = stats.get("knocked", 0)
            knock_wins = stats.get("knock_wins", 0)
            continued = stats.get("continued", 0)
            continue_wins = stats.get("continue_wins", 0)

            knock_rate = knock_wins / knocked if knocked > 0 else 0.5
            continue_rate = continue_wins / continued if continued > 0 else 0.5

            decision = knock_rate >= continue_rate

            logger.info(
                "Knock decision: %s (dw=%d, knock_rate=%.2f, continue_rate=%.2f)",
                "YES" if decision else "NO",
                deadwood,
                knock_rate,
                continue_rate,
            )
            factors += [
                f"Knock win rate: {knock_rate:.2f} ({knocked} samples)",
                f"Continue win rate: {continue_rate:.2f} ({continued} samples)",
            ]
            reasoning = (
                f"{'Knocked' if decision else 'No knock'}: knock win rate {knock_rate:.2f} "
                f"{'>=' if decision else '<'} continue win rate {continue_rate:.2f} (deadwood={deadwood})"
            )

        # Record decision
        self._round_knocks.append((deadwood, decision))
        return decision, reasoning, factors

    def record_round_outcome(self, won: bool, points: int) -> None:
        """Update statistics based on round outcome.

        Should be called after each round with the result.

        Args:
            won: Whether this AI won the round.
            points: Points scored (positive if won, negative if lost).
        """
        win_val = 1 if won else 0

        # Update discard stats
        for card_idx in self._round_discards:
            if card_idx not in self.discard_stats:
                self.discard_stats[card_idx] = {"times": 0, "wins": 0, "points": 0}
            self.discard_stats[card_idx]["times"] += 1
            self.discard_stats[card_idx]["wins"] += win_val
            self.discard_stats[card_idx]["points"] += points

        # Update draw stats
        for bucket, choice in self._round_draws:
            if bucket not in self.draw_stats:
                self.draw_stats[bucket] = {"deck_draws": 0, "deck_wins": 0, "discard_draws": 0, "discard_wins": 0}
            if choice == "deck":
                self.draw_stats[bucket]["deck_draws"] += 1
                self.draw_stats[bucket]["deck_wins"] += win_val
            else:
                self.draw_stats[bucket]["discard_draws"] += 1
                self.draw_stats[bucket]["discard_wins"] += win_val

        # Update knock stats
        for deadwood, did_knock in self._round_knocks:
            if deadwood not in self.knock_stats:
                self.knock_stats[deadwood] = {"knocked": 0, "knock_wins": 0, "continued": 0, "continue_wins": 0}
            if did_knock:
                self.knock_stats[deadwood]["knocked"] += 1
                self.knock_stats[deadwood]["knock_wins"] += win_val
            else:
                self.knock_stats[deadwood]["continued"] += 1
                self.knock_stats[deadwood]["continue_wins"] += win_val

        # Clear round tracking
        self.reset_for_new_hand()

    def save(self) -> None:
        """Save statistics to JSON file."""
        if self.stats_path is None:
            return

        self.stats_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "discard_stats": {str(k): v for k, v in self.discard_stats.items()},
            "draw_stats": self.draw_stats,
            "knock_stats": {str(k): v for k, v in self.knock_stats.items()},
        }

        with open(self.stats_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.debug("Saved statistics to %s", self.stats_path)

    def load(self) -> None:
        """Load statistics from JSON file."""
        if self.stats_path is None or not self.stats_path.exists():
            return

        try:
            with open(self.stats_path) as f:
                data = json.load(f)

            self.discard_stats = {int(k): v for k, v in data.get("discard_stats", {}).items()}
            self.draw_stats = data.get("draw_stats", {})
            self.knock_stats = {int(k): v for k, v in data.get("knock_stats", {}).items()}

            total_samples = sum(s.get("times", 0) for s in self.discard_stats.values())
            logger.info("Loaded statistics from %s (%d samples)", self.stats_path, total_samples)

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load statistics: %s", e)

    def get_stats_summary(self) -> dict:
        """Get a summary of current statistics for debugging."""
        total_discards = sum(s.get("times", 0) for s in self.discard_stats.values())
        total_draws = sum(s.get("deck_draws", 0) + s.get("discard_draws", 0) for s in self.draw_stats.values())
        total_knocks = sum(s.get("knocked", 0) + s.get("continued", 0) for s in self.knock_stats.values())

        return {
            "total_discard_samples": total_discards,
            "total_draw_samples": total_draws,
            "total_knock_samples": total_knocks,
            "cards_with_data": len(self.discard_stats),
        }
