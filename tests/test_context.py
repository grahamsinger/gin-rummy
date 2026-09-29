"""Tests for context-aware AI components."""

from gin_rummy.ai.opponent_model import OpponentModel
from gin_rummy.ai.outs import OutsCalculator
from gin_rummy.ai.thresholds import DynamicThresholdCalculator
from gin_rummy.models import Card, Hand, Rank, Suit
from gin_rummy.models.game_context import GameContext
from gin_rummy.models.outs import OutInfo, OutsAnalysis, OutType


class TestOutsAnalysis:
    """Tests for OutsAnalysis dataclass."""

    def test_empty_analysis(self):
        """Empty analysis should have zero counts."""
        analysis = OutsAnalysis()
        assert analysis.live_out_count == 0
        assert analysis.dead_out_count == 0
        assert analysis.weighted_value == 0.0
        assert len(analysis.all_outs) == 0

    def test_live_out_count(self):
        """Should count only non-dead outs."""
        analysis = OutsAnalysis(
            meld_completing_outs=[
                OutInfo(Card(Rank.ACE, Suit.SPADES), OutType.MELD_COMPLETING, 10.0, "test", is_dead=False),
                OutInfo(Card(Rank.TWO, Suit.SPADES), OutType.MELD_COMPLETING, 10.0, "test", is_dead=True),
            ],
            partial_outs=[
                OutInfo(Card(Rank.THREE, Suit.SPADES), OutType.SET_BUILDING, 5.0, "test", is_dead=False),
            ],
        )
        assert analysis.live_out_count == 2
        assert analysis.dead_out_count == 1

    def test_weighted_value_excludes_dead(self):
        """Weighted value should only count live outs."""
        analysis = OutsAnalysis(
            meld_completing_outs=[
                OutInfo(Card(Rank.ACE, Suit.SPADES), OutType.MELD_COMPLETING, 10.0, "test", is_dead=False),
                OutInfo(Card(Rank.TWO, Suit.SPADES), OutType.MELD_COMPLETING, 10.0, "test", is_dead=True),
            ],
        )
        assert analysis.weighted_value == 10.0  # Only the live out


class TestOutsCalculator:
    """Tests for OutsCalculator."""

    def test_finds_meld_completing_out_for_pair(self):
        """A pair should have 2 meld-completing outs (the other two of that rank)."""
        # Hand with a pair of aces
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.THREE, Suit.CLUBS),
                Card(Rank.FIVE, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.NINE, Suit.HEARTS),
                Card(Rank.JACK, Suit.CLUBS),
                Card(Rank.QUEEN, Suit.DIAMONDS),
                Card(Rank.KING, Suit.SPADES),
                Card(Rank.TEN, Suit.HEARTS),
            ]
        )

        calc = OutsCalculator()
        analysis = calc.calculate_outs(hand, dead_cards=set())

        # Should find A♦ and A♣ as meld-completing outs
        meld_completing_cards = {o.card for o in analysis.meld_completing_outs}
        assert Card(Rank.ACE, Suit.DIAMONDS) in meld_completing_cards
        assert Card(Rank.ACE, Suit.CLUBS) in meld_completing_cards

    def test_finds_meld_completing_out_for_run(self):
        """A 2-card run should have meld-completing outs at both ends."""
        # Hand with 7♥ 8♥ (needs 6♥ or 9♥ to complete)
        hand = Hand(
            [
                Card(Rank.SEVEN, Suit.HEARTS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.THREE, Suit.CLUBS),
                Card(Rank.FIVE, Suit.DIAMONDS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.QUEEN, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.TWO, Suit.SPADES),
                Card(Rank.FOUR, Suit.HEARTS),
            ]
        )

        calc = OutsCalculator()
        analysis = calc.calculate_outs(hand, dead_cards=set())

        # Should find 6♥ and 9♥ as meld-completing outs
        meld_completing_cards = {o.card for o in analysis.meld_completing_outs}
        assert Card(Rank.SIX, Suit.HEARTS) in meld_completing_cards
        assert Card(Rank.NINE, Suit.HEARTS) in meld_completing_cards

    def test_marks_dead_outs(self):
        """Outs that are in dead_cards should be marked as dead."""
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.THREE, Suit.CLUBS),
                Card(Rank.FIVE, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.NINE, Suit.HEARTS),
                Card(Rank.JACK, Suit.CLUBS),
                Card(Rank.QUEEN, Suit.DIAMONDS),
                Card(Rank.KING, Suit.SPADES),
                Card(Rank.TEN, Suit.HEARTS),
            ]
        )

        # Mark A♦ as dead (in discard pile)
        dead_cards = {Card(Rank.ACE, Suit.DIAMONDS)}

        calc = OutsCalculator()
        analysis = calc.calculate_outs(hand, dead_cards=dead_cards)

        # Find the A♦ out - it should be marked dead
        ace_diamond_out = next(
            (o for o in analysis.meld_completing_outs if o.card == Card(Rank.ACE, Suit.DIAMONDS)), None
        )
        assert ace_diamond_out is not None
        assert ace_diamond_out.is_dead is True

        # A♣ should not be dead
        ace_club_out = next((o for o in analysis.meld_completing_outs if o.card == Card(Rank.ACE, Suit.CLUBS)), None)
        assert ace_club_out is not None
        assert ace_club_out.is_dead is False

    def test_pair_outs_are_meld_completing(self):
        """Pairs should have meld-completing outs (not partial) since adding one card creates a set."""
        hand = Hand(
            [
                Card(Rank.FIVE, Suit.SPADES),
                Card(Rank.FIVE, Suit.HEARTS),  # Pair of 5s
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.NINE, Suit.HEARTS),
                Card(Rank.JACK, Suit.CLUBS),
                Card(Rank.QUEEN, Suit.DIAMONDS),
                Card(Rank.KING, Suit.SPADES),
                Card(Rank.TEN, Suit.HEARTS),
            ]
        )

        calc = OutsCalculator()
        analysis = calc.calculate_outs(hand, dead_cards=set(), deck_position_pct=0.1)  # Early game

        # 5♦ and 5♣ complete the 5s set (meld) - they should be meld-completing, not partial
        meld_completing_cards = {o.card for o in analysis.meld_completing_outs}
        assert Card(Rank.FIVE, Suit.DIAMONDS) in meld_completing_cards
        assert Card(Rank.FIVE, Suit.CLUBS) in meld_completing_cards

        # They should NOT be in partial outs (no double counting)
        partial_cards = {o.card for o in analysis.partial_outs}
        assert Card(Rank.FIVE, Suit.DIAMONDS) not in partial_cards
        assert Card(Rank.FIVE, Suit.CLUBS) not in partial_cards

    def test_late_game_reduces_partial_outs(self):
        """Late game should reduce or eliminate partial outs.

        Note: Pairs and 2-card sequences are meld-completing (not partial).
        Partial outs exist for gap scenarios (e.g., 5-7 needing 6).
        """
        hand = Hand(
            [
                Card(Rank.FIVE, Suit.SPADES),
                Card(Rank.SEVEN, Suit.SPADES),  # Gap - 6♠ fills it (partial)
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.NINE, Suit.HEARTS),
                Card(Rank.JACK, Suit.CLUBS),
                Card(Rank.QUEEN, Suit.DIAMONDS),
                Card(Rank.KING, Suit.SPADES),
                Card(Rank.TEN, Suit.HEARTS),
                Card(Rank.TWO, Suit.CLUBS),
            ]
        )

        calc = OutsCalculator()

        # Early game - 6♠ should be a partial out (fills gap)
        early_analysis = calc.calculate_outs(hand, dead_cards=set(), deck_position_pct=0.1)
        early_partial_value = sum(o.weight for o in early_analysis.partial_outs)

        # Late game - partial outs should be reduced/eliminated
        late_analysis = calc.calculate_outs(hand, dead_cards=set(), deck_position_pct=0.9)
        late_partial_value = sum(o.weight for o in late_analysis.partial_outs)

        # Late game partial outs should be worth less (or zero)
        assert late_partial_value <= early_partial_value

    def test_no_double_counting_meld_completing_and_partial(self):
        """Meld-completing outs should not also appear as partial outs.

        A pair like 7♥ 7♠ has outs 7♣ 7♦ that complete a set.
        These should only be counted as meld-completing, not also as partial.
        """
        hand = Hand(
            [
                Card(Rank.SEVEN, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),  # Pair of 7s
                Card(Rank.EIGHT, Suit.SPADES),  # Adjacent to 7♠
                Card(Rank.THREE, Suit.CLUBS),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.TWO, Suit.HEARTS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.DIAMONDS),
                Card(Rank.JACK, Suit.DIAMONDS),
                Card(Rank.TEN, Suit.CLUBS),
            ]
        )

        calc = OutsCalculator()
        analysis = calc.calculate_outs(hand, dead_cards=set(), deck_position_pct=0.0)

        # Get cards from each list
        meld_completing_cards = {o.card for o in analysis.meld_completing_outs}
        partial_cards = {o.card for o in analysis.partial_outs}

        # No overlap - each card should only be counted once
        overlap = meld_completing_cards & partial_cards
        assert overlap == set(), f"Cards counted in both lists: {overlap}"

        # 7♣ and 7♦ should be meld-completing (complete the set)
        assert Card(Rank.SEVEN, Suit.CLUBS) in meld_completing_cards
        assert Card(Rank.SEVEN, Suit.DIAMONDS) in meld_completing_cards

        # When 7♣ and 7♦ die, exactly 2 outs should be lost (not 4)
        dead = {Card(Rank.SEVEN, Suit.CLUBS), Card(Rank.SEVEN, Suit.DIAMONDS)}
        dead_analysis = calc.calculate_outs(hand, dead_cards=dead, deck_position_pct=0.0)

        live_before = analysis.live_out_count
        live_after = dead_analysis.live_out_count
        assert live_before - live_after == 2, f"Expected 2 outs lost when 2 cards die, got {live_before - live_after}"


class TestOpponentModel:
    """Tests for OpponentModel."""

    def test_tracks_discards(self):
        """Should track discards by rank and suit."""
        model = OpponentModel()
        model.record_discard(Card(Rank.KING, Suit.HEARTS))
        model.record_discard(Card(Rank.KING, Suit.SPADES))
        model.record_discard(Card(Rank.QUEEN, Suit.HEARTS))

        assert model.discarded_ranks[Rank.KING] == 2
        assert model.discarded_ranks[Rank.QUEEN] == 1
        assert model.discarded_suits[Suit.HEARTS] == 2
        assert model.discarded_suits[Suit.SPADES] == 1
        assert model.total_discards == 3

    def test_tracks_pickups(self):
        """Should track pickups by rank and suit."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.CLUBS))
        model.record_pickup(Card(Rank.EIGHT, Suit.CLUBS))

        assert model.picked_up_ranks[Rank.SEVEN] == 1
        assert model.picked_up_ranks[Rank.EIGHT] == 1
        assert model.picked_up_suits[Suit.CLUBS] == 2
        assert model.total_pickups == 2

    def test_predict_will_discard_high_for_discarded_ranks(self):
        """Cards of frequently discarded ranks should have higher discard probability."""
        model = OpponentModel()
        # Opponent discards lots of kings
        for _ in range(5):
            model.record_discard(Card(Rank.KING, Suit.HEARTS))

        # Should predict higher probability of discarding another king
        king_prob = model.predict_will_discard(Card(Rank.KING, Suit.SPADES))
        ace_prob = model.predict_will_discard(Card(Rank.ACE, Suit.SPADES))

        assert king_prob > ace_prob

    def test_predict_will_take_high_for_picked_ranks(self):
        """Cards of frequently picked ranks should have higher take probability."""
        model = OpponentModel()
        # Opponent picks up sevens
        model.record_pickup(Card(Rank.SEVEN, Suit.CLUBS))
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))

        # Should predict higher probability of taking another seven
        seven_prob = model.predict_will_take(Card(Rank.SEVEN, Suit.SPADES))
        king_prob = model.predict_will_take(Card(Rank.KING, Suit.SPADES))

        assert seven_prob > king_prob

    def test_reset_clears_all_data(self):
        """Reset should clear all tracking data."""
        model = OpponentModel()
        model.record_discard(Card(Rank.KING, Suit.HEARTS))
        model.record_pickup(Card(Rank.SEVEN, Suit.CLUBS))

        model.reset()

        assert model.total_discards == 0
        assert model.total_pickups == 0
        assert len(model.discarded_ranks) == 0
        assert len(model.picked_up_ranks) == 0


class TestOpponentMeldInference:
    """Tests for opponent meld inference from pickup patterns."""

    def test_infers_set_from_same_rank_pickups(self):
        """Picking up two cards of same rank suggests building a set."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.SEVEN, Suit.SPADES))

        danger = model.get_danger_cards()
        # Other 7s would complete the set
        assert Card(Rank.SEVEN, Suit.DIAMONDS) in danger
        assert Card(Rank.SEVEN, Suit.CLUBS) in danger

    def test_infers_run_from_consecutive_suit_pickups(self):
        """Picking up consecutive cards of same suit suggests building a run."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.EIGHT, Suit.HEARTS))

        danger = model.get_danger_cards()
        # Cards that extend the run are dangerous
        assert Card(Rank.SIX, Suit.HEARTS) in danger
        assert Card(Rank.NINE, Suit.HEARTS) in danger

    def test_infers_run_from_gapped_suit_pickups(self):
        """Picking up same-suit cards with gap of 1 suggests building a run."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.NINE, Suit.HEARTS))

        danger = model.get_danger_cards()
        # The middle card would complete the run
        assert Card(Rank.EIGHT, Suit.HEARTS) in danger

    def test_tracks_specific_picked_up_cards(self):
        """Should track the actual cards picked up, not just counts."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.EIGHT, Suit.CLUBS))

        assert Card(Rank.SEVEN, Suit.HEARTS) in model.picked_up_cards
        assert Card(Rank.EIGHT, Suit.CLUBS) in model.picked_up_cards

    def test_is_card_dangerous_for_inferred_melds(self):
        """is_card_dangerous should return True for cards that complete inferred melds."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.SEVEN, Suit.SPADES))

        # 7♦ would help opponent
        assert model.is_card_dangerous(Card(Rank.SEVEN, Suit.DIAMONDS)) is True
        # K♠ is unrelated
        assert model.is_card_dangerous(Card(Rank.KING, Suit.SPADES)) is False

    def test_reset_clears_inferred_melds(self):
        """Reset should clear inferred melds and picked up cards."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.SEVEN, Suit.SPADES))

        model.reset()

        assert len(model.picked_up_cards) == 0
        assert len(model.inferred_melds) == 0
        assert len(model.get_danger_cards()) == 0

    def test_single_pickup_no_inferred_melds(self):
        """A single pickup should not infer any melds."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))

        # No melds can be inferred from a single card
        assert len(model.inferred_melds) == 0
        assert len(model.get_danger_cards()) == 0

    def test_unrelated_pickups_no_melds(self):
        """Unrelated pickups should not infer melds."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.KING, Suit.CLUBS))

        # These cards don't form any meld pattern
        assert len(model.inferred_melds) == 0

    def test_three_card_run_pickup(self):
        """Three consecutive same-suit pickups should infer a run."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.EIGHT, Suit.HEARTS))
        model.record_pickup(Card(Rank.NINE, Suit.HEARTS))

        danger = model.get_danger_cards()
        # Extensions at both ends
        assert Card(Rank.SIX, Suit.HEARTS) in danger
        assert Card(Rank.TEN, Suit.HEARTS) in danger

    def test_run_at_edge_of_ranks(self):
        """Run at edge (A-2 or Q-K) should only have one extension."""
        model = OpponentModel()
        model.record_pickup(Card(Rank.QUEEN, Suit.HEARTS))
        model.record_pickup(Card(Rank.KING, Suit.HEARTS))

        danger = model.get_danger_cards()
        # Only Jack extends (Ace doesn't continue runs in gin rummy)
        assert Card(Rank.JACK, Suit.HEARTS) in danger
        assert Card(Rank.ACE, Suit.HEARTS) not in danger


class TestDynamicThresholdCalculator:
    """Tests for DynamicThresholdCalculator."""

    def test_base_threshold_with_neutral_context(self):
        """Should return close to base threshold with neutral context."""
        calc = DynamicThresholdCalculator()
        context = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,  # Mid game
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=50,
            opponent_score=50,  # Even score
        )
        context.my_outs = OutsAnalysis()  # No outs

        threshold = calc.calculate_threshold(context)
        # Should be close to base (1), maybe slightly modified
        assert 0 <= threshold <= 3

    def test_late_game_lowers_threshold(self):
        """Late game should lower threshold (more aggressive)."""
        calc = DynamicThresholdCalculator()

        early_context = GameContext(
            deck_remaining=30,
            deck_position_pct=0.1,  # Early
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=50,
            opponent_score=50,
        )
        early_context.my_outs = OutsAnalysis()

        late_context = GameContext(
            deck_remaining=5,
            deck_position_pct=0.85,  # Late
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=50,
            opponent_score=50,
        )
        late_context.my_outs = OutsAnalysis()

        early_threshold = calc.calculate_threshold(early_context)
        late_threshold = calc.calculate_threshold(late_context)

        assert late_threshold <= early_threshold

    def test_many_outs_raises_threshold(self):
        """Having many outs should raise threshold (can afford to wait)."""
        calc = DynamicThresholdCalculator()

        # Create analysis with many outs
        many_outs = OutsAnalysis(
            meld_completing_outs=[
                OutInfo(Card(Rank.ACE, Suit.SPADES), OutType.MELD_COMPLETING, 10.0, "test") for _ in range(15)
            ]
        )
        few_outs = OutsAnalysis()

        context_many = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=50,
            opponent_score=50,
            my_outs=many_outs,
        )

        context_few = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=50,
            opponent_score=50,
            my_outs=few_outs,
        )

        threshold_many = calc.calculate_threshold(context_many)
        threshold_few = calc.calculate_threshold(context_few)

        assert threshold_many >= threshold_few

    def test_trailing_score_lowers_threshold(self):
        """Trailing badly should lower threshold (more aggressive)."""
        calc = DynamicThresholdCalculator()

        trailing_context = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=20,
            opponent_score=80,  # Trailing by 60
        )
        trailing_context.my_outs = OutsAnalysis()

        leading_context = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=80,
            opponent_score=20,  # Leading by 60
        )
        leading_context.my_outs = OutsAnalysis()

        trailing_threshold = calc.calculate_threshold(trailing_context)
        leading_threshold = calc.calculate_threshold(leading_context)

        assert trailing_threshold < leading_threshold

    def test_threshold_clamped_to_range(self):
        """Threshold should always be between 0 and 5."""
        calc = DynamicThresholdCalculator()

        # Extreme context that might push threshold out of range
        extreme_context = GameContext(
            deck_remaining=2,
            deck_position_pct=0.95,  # Very late
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=10,
            opponent_score=90,  # Trailing badly
        )
        extreme_context.my_outs = OutsAnalysis()

        threshold = calc.calculate_threshold(extreme_context)
        assert 0 <= threshold <= 5


class TestOutsCalculatorRealHands:
    """Tests for OutsCalculator with real game hands."""

    def test_hand_with_multiple_pairs(self):
        """Hand with multiple pairs should identify all set-completing outs.

        Hand:
          ♠: 3♠, 8♠
          ♥: 2♥
          ♦: 2♦, 3♦, 6♦, K♦
          ♣: 6♣, 8♣, K♣

        Expected meld-completing outs:
          - 2♠, 2♣ (complete set of 2s)
          - 3♥, 3♣ (complete set of 3s)
          - 6♠, 6♥ (complete set of 6s)
          - 8♦, 8♥ (complete set of 8s)
          - K♠, K♥ (complete set of Ks)
        """
        hand = Hand(
            [
                Card(Rank.THREE, Suit.SPADES),
                Card(Rank.EIGHT, Suit.SPADES),
                Card(Rank.TWO, Suit.HEARTS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.SIX, Suit.DIAMONDS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.EIGHT, Suit.CLUBS),
                Card(Rank.KING, Suit.CLUBS),
            ]
        )

        calc = OutsCalculator()
        analysis = calc.calculate_outs(hand, dead_cards=set())

        meld_completing_cards = {o.card for o in analysis.meld_completing_outs}

        # Check for 2s (we have 2♥, 2♦)
        assert Card(Rank.TWO, Suit.SPADES) in meld_completing_cards, "2♠ should complete set of 2s"
        assert Card(Rank.TWO, Suit.CLUBS) in meld_completing_cards, "2♣ should complete set of 2s"

        # Check for 3s (we have 3♠, 3♦)
        assert Card(Rank.THREE, Suit.HEARTS) in meld_completing_cards, "3♥ should complete set of 3s"
        assert Card(Rank.THREE, Suit.CLUBS) in meld_completing_cards, "3♣ should complete set of 3s"

        # Check for 6s (we have 6♦, 6♣)
        assert Card(Rank.SIX, Suit.SPADES) in meld_completing_cards, "6♠ should complete set of 6s"
        assert Card(Rank.SIX, Suit.HEARTS) in meld_completing_cards, "6♥ should complete set of 6s"

        # Check for 8s (we have 8♠, 8♣)
        assert Card(Rank.EIGHT, Suit.DIAMONDS) in meld_completing_cards, "8♦ should complete set of 8s"
        assert Card(Rank.EIGHT, Suit.HEARTS) in meld_completing_cards, "8♥ should complete set of 8s"

        # Check for Ks (we have K♦, K♣)
        assert Card(Rank.KING, Suit.SPADES) in meld_completing_cards, "K♠ should complete set of Ks"
        assert Card(Rank.KING, Suit.HEARTS) in meld_completing_cards, "K♥ should complete set of Ks"

    def test_hand_with_run_potential(self):
        """Hand with 2-card run should identify run-completing outs.

        Hand with 2♦, 3♦ should find 4♦ and A♦ as run-completing outs.
        """
        hand = Hand(
            [
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.EIGHT, Suit.SPADES),
                Card(Rank.TEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.HEARTS),
                Card(Rank.QUEEN, Suit.CLUBS),
                Card(Rank.KING, Suit.CLUBS),
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.FIVE, Suit.HEARTS),
            ]
        )

        calc = OutsCalculator()
        analysis = calc.calculate_outs(hand, dead_cards=set())

        meld_completing_cards = {o.card for o in analysis.meld_completing_outs}

        # 2♦-3♦ needs A♦ or 4♦ to complete
        assert Card(Rank.ACE, Suit.DIAMONDS) in meld_completing_cards, "A♦ should complete 2-3 run"
        assert Card(Rank.FOUR, Suit.DIAMONDS) in meld_completing_cards, "4♦ should complete 2-3 run"


class TestGameContext:
    """Tests for GameContext dataclass."""

    def test_score_differential(self):
        """Score differential should be my_score - opponent_score."""
        context = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=70,
            opponent_score=40,
        )
        assert context.score_differential == 30  # Leading

        context2 = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=30,
            opponent_score=80,
        )
        assert context2.score_differential == -50  # Trailing

    def test_points_to_win(self):
        """Points to win should be target - my_score, minimum 0."""
        context = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            discard_history=[],
            opponent_pickups=[],
            my_pickups=[],
            my_score=75,
            opponent_score=40,
            target_score=100,
        )
        assert context.points_to_win == 25
        assert context.opponent_points_to_win == 60
