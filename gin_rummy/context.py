"""Context-aware AI support: game state tracking, outs calculation, opponent modeling."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from gin_rummy.card import Card, Suit, Rank
from gin_rummy.melds import find_all_melds, Meld, MeldType

if TYPE_CHECKING:
    from gin_rummy.hand import Hand
    from gin_rummy.config import ContextAwareAIConfig


class CardLocation(Enum):
    """Where a card is located from a player's perspective."""

    MY_HAND = auto()  # In my current hand
    OPPONENT_HAND_KNOWN = auto()  # Opponent picked from discard, not re-discarded
    DISCARD_TOP = auto()  # Top of discard pile (available to take)
    DISCARD_BURIED = auto()  # Previously discarded, now buried under other cards
    UNKNOWN = auto()  # In deck or opponent's initial hand (can't distinguish)


class OutType(Enum):
    """Type of 'out' - how a card would help the hand."""

    MELD_COMPLETING = auto()  # Completes a 3+ card meld
    RUN_EXTENDING = auto()  # Extends an existing run by 1
    SET_BUILDING = auto()  # Creates a pair or adds to a pair


@dataclass
class OutInfo:
    """Information about a single 'out' card."""

    card: Card
    out_type: OutType
    weight: float  # Weighted value (higher = more valuable)
    description: str  # e.g., "completes 7-8-9 hearts run"
    is_dead: bool = False  # True if card is known to be unavailable


@dataclass
class OutsAnalysis:
    """Complete outs analysis for a hand."""

    meld_completing_outs: list[OutInfo] = field(default_factory=list)
    partial_outs: list[OutInfo] = field(default_factory=list)

    @property
    def all_outs(self) -> list[OutInfo]:
        """All outs combined."""
        return self.meld_completing_outs + self.partial_outs

    @property
    def live_out_count(self) -> int:
        """Count of outs that are not dead."""
        return sum(1 for o in self.all_outs if not o.is_dead)

    @property
    def dead_out_count(self) -> int:
        """Count of outs that are known dead."""
        return sum(1 for o in self.all_outs if o.is_dead)

    @property
    def weighted_value(self) -> float:
        """Sum of weighted values of all live outs."""
        return sum(o.weight for o in self.all_outs if not o.is_dead)

    @property
    def live_meld_completing_cards(self) -> set[Card]:
        """Set of live meld-completing out cards."""
        return {o.card for o in self.meld_completing_outs if not o.is_dead}


@dataclass
class KnownCards:
    """Unified card location tracking from one player's perspective.

    Tracks where all cards are located based on observable game events.
    This is the single source of truth for card availability.
    """

    my_hand: frozenset[Card]
    opponent_hand_known: frozenset[Card]  # Picked from discard, not re-discarded
    discard_top: Card | None  # Available to take
    discard_buried: frozenset[Card]  # Previously discarded, now inaccessible

    def get_location(self, card: Card) -> CardLocation:
        """Determine where a card is located."""
        if card in self.my_hand:
            return CardLocation.MY_HAND
        if card in self.opponent_hand_known:
            return CardLocation.OPPONENT_HAND_KNOWN
        if card == self.discard_top:
            return CardLocation.DISCARD_TOP
        if card in self.discard_buried:
            return CardLocation.DISCARD_BURIED
        return CardLocation.UNKNOWN

    @property
    def dead_cards(self) -> frozenset[Card]:
        """Cards unavailable to draw: opponent's known hand + buried discards.

        Note: Does NOT include discard_top (that's available) or my_hand.
        """
        return self.opponent_hand_known | self.discard_buried


@dataclass
class GameContext:
    """Snapshot of game state for AI decision-making."""

    # Deck state
    deck_remaining: int
    deck_position_pct: float  # 0.0 = full deck, 1.0 = nearly empty

    # Score context (required fields)
    my_score: int
    opponent_score: int

    # Unified card tracking
    known_cards: KnownCards | None = None

    # Legacy fields for backwards compatibility (OpponentModel uses these)
    discard_history: list[Card] = field(default_factory=list)
    opponent_pickups: list[Card] = field(default_factory=list)
    my_pickups: list[Card] = field(default_factory=list)

    target_score: int = 100

    # Current hand analysis (set by AI after construction)
    my_outs: OutsAnalysis | None = None

    @property
    def dead_cards(self) -> set[Card]:
        """All known unavailable cards. Uses KnownCards if available."""
        if self.known_cards:
            return set(self.known_cards.dead_cards)
        # Fallback for backwards compatibility
        return set(self.discard_history)

    @property
    def score_differential(self) -> int:
        """Positive = leading, negative = trailing."""
        return self.my_score - self.opponent_score

    @property
    def points_to_win(self) -> int:
        """Points I need to win."""
        return max(0, self.target_score - self.my_score)

    @property
    def opponent_points_to_win(self) -> int:
        """Points opponent needs to win."""
        return max(0, self.target_score - self.opponent_score)


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
        analysis.meld_completing_outs = self._find_meld_completing_outs(
            hand_cards, dead_cards, deck_position_pct
        )

        # Find partial outs (pairs, run extensions) - weighted by game phase
        analysis.partial_outs = self._find_partial_outs(
            hand_cards, dead_cards, deck_position_pct
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
                        meld_is_new = not any(
                            set(m.cards) == set(meld.cards) for m in old_melds
                        )
                        if meld_is_new:
                            is_dead = card in dead_cards
                            meld_type_str = (
                                "set" if meld.meld_type == MeldType.SET else "run"
                            )
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
    ) -> list[OutInfo]:
        """Find cards that build toward melds (pairs, run extensions).

        These are less valuable than meld-completing outs, especially
        late in the game.
        """
        outs: list[OutInfo] = []

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
                    if card not in hand_cards:
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
                        if card not in hand_cards:
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
                        if card not in hand_cards:
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
                    if card not in hand_cards:
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

    def record_discard(self, card: Card) -> None:
        """Record that opponent discarded a card."""
        self.discarded_ranks[card.rank] += 1
        self.discarded_suits[card.suit] += 1
        self.total_discards += 1

    def record_pickup(self, card: Card) -> None:
        """Record that opponent picked up a card from discard."""
        self.picked_up_ranks[card.rank] += 1
        self.picked_up_suits[card.suit] += 1
        self.total_pickups += 1

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


class DynamicThresholdCalculator:
    """Calculates dynamic min_deadwood_improvement threshold based on game context."""

    def __init__(self, config: ContextAwareAIConfig | None = None) -> None:
        """Initialize with optional config."""
        if config:
            self.base_threshold = config.base_draw_threshold
            self.max_deck_modifier = config.max_deck_modifier
            self.max_outs_modifier = config.max_outs_modifier
            self.trailing_threshold = config.trailing_aggressive_threshold
            self.leading_threshold = config.leading_conservative_threshold
        else:
            self.base_threshold = 1
            self.max_deck_modifier = 2.0
            self.max_outs_modifier = 2.0
            self.trailing_threshold = 50
            self.leading_threshold = 30

    def calculate_threshold(self, context: GameContext) -> int:
        """Calculate the dynamic draw threshold based on game context.

        Returns:
            Minimum deadwood improvement needed to take from discard.
            Lower = more aggressive, Higher = more conservative.
        """
        base = float(self.base_threshold)

        # Deck position: late game = more desperate = lower threshold
        # deck_position_pct: 0 = full, 1 = empty
        deck_modifier = -self.max_deck_modifier * context.deck_position_pct

        # Outs: many live outs = can afford to wait = higher threshold
        outs_modifier = 0.0
        if context.my_outs:
            outs_modifier = min(
                context.my_outs.live_out_count / 10.0, self.max_outs_modifier
            )

        # Score pressure
        score_modifier = 0.0
        if context.score_differential < -self.trailing_threshold:
            score_modifier = -2.0  # Very aggressive when trailing badly
        elif context.score_differential < -20:
            score_modifier = -1.0  # Somewhat aggressive
        elif context.score_differential > self.leading_threshold:
            score_modifier = 1.0  # Conservative when leading

        threshold = base + deck_modifier + outs_modifier + score_modifier

        # Clamp to reasonable range
        return max(0, min(5, int(threshold)))
