"""Opponent modelling: what the opponent's discards and pickups say about their hand."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gin_rummy.models import Card, MeldType, Rank, Suit
from gin_rummy.models.game_context import GameContext

if TYPE_CHECKING:
    pass


@dataclass
class InferredMeld:
    """A meld we believe opponent is building based on their pickups."""

    cards: frozenset[Card]  # Cards we know they picked up for this meld
    meld_type: MeldType  # SET or RUN
    completing_cards: frozenset[Card]  # Cards that would complete/extend this meld
    confidence: float = 1.0  # 0.0 to 1.0 (for future use)


@dataclass
class OpponentModel:
    """Tracks opponent behavior patterns to predict future actions."""

    # What they've discarded
    discarded_ranks: Counter[Rank] = field(default_factory=Counter)
    discarded_suits: Counter[Suit] = field(default_factory=Counter)

    # What they've picked up from discard
    picked_up_ranks: Counter[Rank] = field(default_factory=Counter)
    picked_up_suits: Counter[Suit] = field(default_factory=Counter)

    # Total observations for confidence weighting
    total_discards: int = 0
    total_pickups: int = 0

    # Specific cards picked up (for meld inference)
    picked_up_cards: list[Card] = field(default_factory=list)

    # Specific cards discarded (for hand-sampling inference)
    discarded_cards: list[Card] = field(default_factory=list)

    # Inferred melds opponent is building
    inferred_melds: list[InferredMeld] = field(default_factory=list)

    def record_discard(self, card: Card) -> None:
        """Record that opponent discarded a card."""
        self.discarded_ranks[card.rank] += 1
        self.discarded_suits[card.suit] += 1
        self.total_discards += 1
        self.discarded_cards.append(card)

        # If they throw back a card they previously picked up, they are no
        # longer holding it - un-track it so inferred melds/danger cards
        # don't stay poisoned for the rest of the hand
        if card in self.picked_up_cards:
            self.picked_up_cards.remove(card)
            self.picked_up_ranks[card.rank] -= 1
            self.picked_up_suits[card.suit] -= 1
            self.total_pickups -= 1
            self._update_inferred_melds()

    def record_pickup(self, card: Card) -> None:
        """Record that opponent picked up a card from discard."""
        self.picked_up_ranks[card.rank] += 1
        self.picked_up_suits[card.suit] += 1
        self.total_pickups += 1
        self.picked_up_cards.append(card)
        self._update_inferred_melds()

    def _update_inferred_melds(self) -> None:
        """Analyze picked_up_cards to infer what melds opponent is building."""
        self.inferred_melds.clear()

        if len(self.picked_up_cards) < 2:
            return

        # Group cards by rank (for set detection)
        by_rank: dict[Rank, list[Card]] = {}
        for card in self.picked_up_cards:
            if card.rank not in by_rank:
                by_rank[card.rank] = []
            by_rank[card.rank].append(card)

        # Detect sets: 2+ cards of same rank
        for rank, cards in by_rank.items():
            if len(cards) >= 2:
                # Find remaining cards of this rank that would complete the set
                completing = frozenset(Card(rank, suit) for suit in Suit if Card(rank, suit) not in cards)
                self.inferred_melds.append(
                    InferredMeld(
                        cards=frozenset(cards),
                        meld_type=MeldType.SET,
                        completing_cards=completing,
                    )
                )

        # Group cards by suit (for run detection)
        by_suit: dict[Suit, list[Card]] = {}
        for card in self.picked_up_cards:
            if card.suit not in by_suit:
                by_suit[card.suit] = []
            by_suit[card.suit].append(card)

        # Detect runs: cards of same suit that are consecutive or have gap of 1
        for suit, cards in by_suit.items():
            if len(cards) < 2:
                continue

            # Sort by rank value
            sorted_cards = sorted(cards, key=lambda c: c.rank.value)

            # Find consecutive sequences or gaps
            i = 0
            while i < len(sorted_cards):
                run_cards = [sorted_cards[i]]

                # Extend run as far as possible
                j = i + 1
                while j < len(sorted_cards):
                    prev_val = sorted_cards[j - 1].rank.value
                    curr_val = sorted_cards[j].rank.value
                    gap = curr_val - prev_val

                    if gap <= 2:  # Consecutive or gap of 1
                        run_cards.append(sorted_cards[j])
                        j += 1
                    else:
                        break

                if len(run_cards) >= 2:
                    completing = self._find_run_completing_cards(run_cards, suit)
                    if completing:
                        self.inferred_melds.append(
                            InferredMeld(
                                cards=frozenset(run_cards),
                                meld_type=MeldType.RUN,
                                completing_cards=completing,
                            )
                        )

                i = j if j > i + 1 else i + 1

    def _find_run_completing_cards(self, run_cards: list[Card], suit: Suit) -> frozenset[Card]:
        """Find cards that would complete or extend a run."""
        completing: set[Card] = set()
        values = sorted(c.rank.value for c in run_cards)

        # Check for gaps within the run
        for i in range(len(values) - 1):
            gap = values[i + 1] - values[i]
            if gap == 2:
                # There's a gap - the middle card completes it
                middle_rank = Rank(values[i] + 1)
                completing.add(Card(middle_rank, suit))

        # Extensions at the ends
        min_val = min(values)
        max_val = max(values)

        # Lower extension (but not below Ace=1)
        if min_val > 1:
            completing.add(Card(Rank(min_val - 1), suit))

        # Upper extension (but not above King=13)
        if max_val < 13:
            completing.add(Card(Rank(max_val + 1), suit))

        return frozenset(completing)

    def get_danger_cards(self) -> set[Card]:
        """Return cards that would help opponent complete inferred melds."""
        danger: set[Card] = set()
        for meld in self.inferred_melds:
            danger.update(meld.completing_cards)
        return danger

    def is_card_dangerous(self, card: Card) -> bool:
        """Check if discarding this card would help opponent."""
        return card in self.get_danger_cards()

    def predict_will_discard(self, card: Card) -> float:
        """Predict probability (0-1) opponent might discard this card.

        Higher probability for ranks/suits they've discarded before.
        """
        if self.total_discards == 0:
            return 0.5  # No data, assume neutral

        # Weight by how often they discard this rank/suit
        rank_freq = self.discarded_ranks[card.rank] / max(self.total_discards, 1)
        suit_freq = self.discarded_suits[card.suit] / max(self.total_discards, 1)

        # Combine with slight preference for rank over suit
        base_prob = 0.6 * rank_freq + 0.4 * suit_freq

        # Adjust: if they picked up this rank, less likely to discard
        if self.picked_up_ranks[card.rank] > 0:
            base_prob *= 0.5

        return min(1.0, base_prob * 2)  # Scale up since frequencies are low

    def predict_will_take(self, card: Card) -> float:
        """Predict probability (0-1) opponent would take this card.

        Higher probability for ranks/suits they've picked up before.
        """
        if self.total_pickups == 0:
            return 0.3  # No data, assume somewhat unlikely

        # Weight by how often they pick up this rank/suit
        rank_freq = self.picked_up_ranks[card.rank] / max(self.total_pickups, 1)
        suit_freq = self.picked_up_suits[card.suit] / max(self.total_pickups, 1)

        # Combine with slight preference for rank (sets) over suit (runs)
        base_prob = 0.6 * rank_freq + 0.4 * suit_freq

        # Adjust: if they discard this rank a lot, less likely to want
        if self.discarded_ranks[card.rank] > 1:
            base_prob *= 0.5

        return min(1.0, base_prob * 3)  # Scale up since frequencies are low

    def is_rank_safe(self, rank: Rank) -> bool:
        """Check if a rank is safe to discard (opponent discarded this rank).

        If opponent discarded a card of this rank, they're likely not
        building a set of that rank, making it safer to discard.

        Args:
            rank: The rank to check.

        Returns:
            True if opponent has discarded this rank at least once.
        """
        return self.discarded_ranks[rank] > 0

    def is_rank_dangerous(self, rank: Rank) -> bool:
        """Check if a rank is dangerous to discard (opponent picked up this rank).

        If opponent picked up a card of this rank, they're likely building
        a set and would want more cards of this rank.

        Args:
            rank: The rank to check.

        Returns:
            True if opponent has picked up this rank at least once.
        """
        return self.picked_up_ranks[rank] > 0

    def is_suit_dangerous(self, suit: Suit) -> bool:
        """Check if a suit is dangerous to discard (opponent picked up this suit).

        If opponent picked up cards of this suit, they're likely building
        a run and would want more cards of this suit.

        Args:
            suit: The suit to check.

        Returns:
            True if opponent has picked up this suit at least once.
        """
        return self.picked_up_suits[suit] > 0

    def reset(self) -> None:
        """Reset all tracking for a new hand."""
        self.discarded_ranks.clear()
        self.discarded_suits.clear()
        self.picked_up_ranks.clear()
        self.picked_up_suits.clear()
        self.total_discards = 0
        self.total_pickups = 0
        self.picked_up_cards.clear()
        self.discarded_cards.clear()
        self.inferred_melds.clear()

    def estimate_deadwood(self, context: GameContext) -> int:
        """Estimate opponent's current deadwood based on observable behavior.

        Uses several heuristics:
        - Base estimate decreases as game progresses (hands improve over time)
        - Each pickup from discard suggests meld building (-2 per pickup)
        - Each inferred meld suggests completed melds (-4 per meld)
        - High card discards suggest opponent has melds to hold (-1 per face card)

        Args:
            context: Current game context with deck position.

        Returns:
            Estimated opponent deadwood (clamped to 0-100 range).
        """
        # Base estimate: starts at 35, decreases as game progresses
        # deck_position_pct: 0.0 = full deck, 1.0 = nearly empty
        base = 35 - int(20 * context.deck_position_pct)

        # Adjust for pickups (each suggests active meld building)
        pickup_adjustment = -2 * self.total_pickups

        # Adjust for inferred melds (likely completed or near-complete)
        meld_adjustment = -4 * len(self.inferred_melds)

        # Count high card discards (10, J, Q, K) - suggests they have melds to hold
        high_ranks = {Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING}
        high_card_discards = sum(1 for rank in self.discarded_ranks.elements() if rank in high_ranks)
        high_card_adjustment = -1 * high_card_discards

        estimated = base + pickup_adjustment + meld_adjustment + high_card_adjustment

        # Clamp to reasonable range
        return max(0, min(100, estimated))

    def estimate_threat_level(self, context: GameContext) -> float:
        """Estimate how threatening the opponent is (0.0-1.0).

        Higher threat = opponent likely has low deadwood and may undercut.

        Factors:
        - Estimated deadwood (lower = more threatening)
        - Number of inferred melds (more = more threatening)
        - Game position (late game with active opponent = more threatening)

        Args:
            context: Current game context.

        Returns:
            Threat level from 0.0 (minimal) to 1.0 (maximum).
        """
        # Base threat from estimated deadwood
        # If estimated at 0, threat = 1.0; if at 30+, threat = 0.0
        estimated_dw = self.estimate_deadwood(context)
        deadwood_threat = max(0.0, 1.0 - (estimated_dw / 30.0))

        # Threat from inferred melds (each meld adds 0.1, capped at 0.3)
        meld_threat = min(0.3, len(self.inferred_melds) * 0.1)

        # Late game threat bonus (opponent still in game = dangerous)
        late_game_bonus = 0.0
        if context.deck_position_pct > 0.5:
            late_game_bonus = 0.1 * (context.deck_position_pct - 0.5) * 2

        # Combine factors (weighted average)
        threat = 0.6 * deadwood_threat + 0.25 * meld_threat + 0.15 * late_game_bonus

        return min(1.0, max(0.0, threat))
