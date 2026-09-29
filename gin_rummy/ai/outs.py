"""Outs calculation: which cards would improve a hand, and how much they are worth."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from gin_rummy.models import Card, MeldType, Rank, Suit, find_all_melds
from gin_rummy.models.outs import OutInfo, OutsAnalysis, OutType

if TYPE_CHECKING:
    from gin_rummy.config import ContextAwareAIConfig
    from gin_rummy.models import Hand


class OutsCalculator:
    """Calculates 'outs' - cards that would help improve a hand."""

    def __init__(self, config: ContextAwareAIConfig | None = None) -> None:
        """Initialize with optional config for weights."""
        # Default weights if no config provided
        if config:
            self.meld_completing_weight = config.meld_completing_weight
            self.run_extending_weight = config.run_extending_weight
            self.set_building_weight = config.set_building_weight
            self.partial_meld_early_bonus = config.partial_meld_early_bonus
            self.early_game_threshold = config.early_game_threshold
            self.late_game_threshold = config.late_game_threshold
        else:
            self.meld_completing_weight = 10.0
            self.run_extending_weight = 5.0
            self.set_building_weight = 4.0
            self.partial_meld_early_bonus = 2.0
            self.early_game_threshold = 0.7
            self.late_game_threshold = 0.3

    def calculate_outs(
        self,
        hand: Hand,
        dead_cards: set[Card],
        deck_position_pct: float = 0.0,
    ) -> OutsAnalysis:
        """Calculate all outs for a hand.

        Args:
            hand: The current hand to analyze.
            dead_cards: Cards known to be unavailable (discard pile, etc.).
            deck_position_pct: 0.0 = early game, 1.0 = late game.

        Returns:
            OutsAnalysis with all identified outs.
        """
        hand_cards = set(hand)
        analysis = OutsAnalysis()

        # Find meld-completing outs
        analysis.meld_completing_outs = self._find_meld_completing_outs(hand_cards, dead_cards, deck_position_pct)

        # Find partial outs (pairs, run extensions) - weighted by game phase
        # Exclude cards already counted as meld-completing to avoid double-counting
        meld_completing_cards = {o.card for o in analysis.meld_completing_outs}
        analysis.partial_outs = self._find_partial_outs(
            hand_cards, dead_cards, deck_position_pct, meld_completing_cards
        )

        return analysis

    def _find_meld_completing_outs(
        self,
        hand_cards: set[Card],
        dead_cards: set[Card],
        deck_position_pct: float,
    ) -> list[OutInfo]:
        """Find cards that would complete a meld (set or run).

        A meld-completing out is a card that, when added to the hand,
        creates a new 3+ card meld.
        """
        outs: list[OutInfo] = []

        # Check each card not in hand
        for suit in Suit:
            for rank in Rank:
                card = Card(rank, suit)
                if card in hand_cards:
                    continue

                # Try adding this card and see if it creates a new meld
                test_cards = list(hand_cards) + [card]
                new_melds = find_all_melds(test_cards)

                # Check if any meld includes this card and wasn't possible before
                for meld in new_melds:
                    if card in meld.cards:
                        # Verify this meld wasn't already possible
                        old_melds = find_all_melds(list(hand_cards))
                        meld_is_new = not any(set(m.cards) == set(meld.cards) for m in old_melds)
                        if meld_is_new:
                            is_dead = card in dead_cards
                            meld_type_str = "set" if meld.meld_type == MeldType.SET else "run"
                            cards_str = " ".join(str(c) for c in meld.cards)
                            outs.append(
                                OutInfo(
                                    card=card,
                                    out_type=OutType.MELD_COMPLETING,
                                    weight=self.meld_completing_weight,
                                    description=f"completes {meld_type_str}: {cards_str}",
                                    is_dead=is_dead,
                                )
                            )
                            break  # Only count card once even if it completes multiple melds

        return outs

    def _find_partial_outs(
        self,
        hand_cards: set[Card],
        dead_cards: set[Card],
        deck_position_pct: float,
        exclude_cards: set[Card] | None = None,
    ) -> list[OutInfo]:
        """Find cards that build toward melds (pairs, run extensions).

        These are less valuable than meld-completing outs, especially
        late in the game.

        Args:
            hand_cards: Cards in hand.
            dead_cards: Cards known to be unavailable.
            deck_position_pct: Game progress (0.0 = early, 1.0 = late).
            exclude_cards: Cards to skip (e.g., already counted as meld-completing).
        """
        outs: list[OutInfo] = []
        exclude = exclude_cards or set()

        # Calculate game phase multiplier
        if deck_position_pct < (1 - self.early_game_threshold):
            phase_mult = 1.0 + self.partial_meld_early_bonus  # Early game bonus
        elif deck_position_pct > (1 - self.late_game_threshold):
            phase_mult = 0.2  # Late game - partial outs worth little
        else:
            phase_mult = 1.0  # Mid game

        # Skip partial outs in very late game
        if phase_mult < 0.3:
            return outs

        # Find pairs (could become sets)
        rank_counts: Counter[Rank] = Counter(c.rank for c in hand_cards)
        for rank, count in rank_counts.items():
            if count == 2:
                # We have a pair - find the other two cards of this rank
                for suit in Suit:
                    card = Card(rank, suit)
                    if card not in hand_cards and card not in exclude:
                        is_dead = card in dead_cards
                        weight = self.set_building_weight * phase_mult
                        outs.append(
                            OutInfo(
                                card=card,
                                out_type=OutType.SET_BUILDING,
                                weight=weight,
                                description=f"extends pair of {rank.short_name}s to set",
                                is_dead=is_dead,
                            )
                        )

        # Find run extensions (2-card sequences that could become runs)
        for suit in Suit:
            suit_cards = sorted(
                [c for c in hand_cards if c.suit == suit],
                key=lambda c: c.rank.value,
            )

            for i in range(len(suit_cards) - 1):
                c1, c2 = suit_cards[i], suit_cards[i + 1]
                diff = c2.rank.value - c1.rank.value

                if diff == 1:
                    # Consecutive pair - can extend on either end
                    # Lower extension
                    if c1.rank.value > 1:  # Not an ace
                        lower_rank = Rank(c1.rank.value - 1)
                        card = Card(lower_rank, suit)
                        if card not in hand_cards and card not in exclude:
                            is_dead = card in dead_cards
                            weight = self.run_extending_weight * phase_mult
                            outs.append(
                                OutInfo(
                                    card=card,
                                    out_type=OutType.RUN_EXTENDING,
                                    weight=weight,
                                    description=f"extends {c1}-{c2} run",
                                    is_dead=is_dead,
                                )
                            )

                    # Upper extension
                    if c2.rank.value < 13:  # Not a king
                        upper_rank = Rank(c2.rank.value + 1)
                        card = Card(upper_rank, suit)
                        if card not in hand_cards and card not in exclude:
                            is_dead = card in dead_cards
                            weight = self.run_extending_weight * phase_mult
                            outs.append(
                                OutInfo(
                                    card=card,
                                    out_type=OutType.RUN_EXTENDING,
                                    weight=weight,
                                    description=f"extends {c1}-{c2} run",
                                    is_dead=is_dead,
                                )
                            )

                elif diff == 2:
                    # Gap of 1 - middle card completes run
                    middle_rank = Rank(c1.rank.value + 1)
                    card = Card(middle_rank, suit)
                    if card not in hand_cards and card not in exclude:
                        is_dead = card in dead_cards
                        # This is actually meld-completing, but caught here as partial
                        # The meld-completing check should find it too
                        weight = self.run_extending_weight * phase_mult
                        outs.append(
                            OutInfo(
                                card=card,
                                out_type=OutType.RUN_EXTENDING,
                                weight=weight,
                                description=f"fills gap between {c1} and {c2}",
                                is_dead=is_dead,
                            )
                        )

        return outs
