"""Tests for AI module."""

import pytest

from gin_rummy.ai import BasicAI, ContextAwareAI, DrawChoice
from gin_rummy.context import GameContext, OpponentModel
from gin_rummy.models import Card, Hand, Rank, Suit
from tests.helpers import make_ai_config as make_test_config


class TestBasicAI:
    def test_decide_draw_from_deck_when_no_discard(self):
        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.THREE, Suit.HEARTS),
            ]
        )
        choice = ai.decide_draw(hand, None)
        assert choice == DrawChoice.DECK

    def test_decide_draw_takes_helpful_card(self):
        ai = BasicAI()
        # Hand with two aces - third ace would form a set
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.KING, Suit.CLUBS),
            ]
        )
        # Discard is third ace
        discard = Card(Rank.ACE, Suit.CLUBS)
        choice = ai.decide_draw(hand, discard)
        assert choice == DrawChoice.DISCARD

    def test_decide_draw_ignores_unhelpful_card(self):
        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.THREE, Suit.HEARTS),
                Card(Rank.FIVE, Suit.CLUBS),
            ]
        )
        # Discard doesn't help
        discard = Card(Rank.KING, Suit.DIAMONDS)
        choice = ai.decide_draw(hand, discard)
        assert choice == DrawChoice.DECK

    def test_decide_discard_removes_highest_deadwood(self):
        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),  # 1
                Card(Rank.TWO, Suit.HEARTS),  # 2
                Card(Rank.KING, Suit.CLUBS),  # 10 - highest deadwood
            ]
        )
        discard = ai.decide_discard(hand)
        # Should discard King (highest deadwood not in meld)
        assert discard == Card(Rank.KING, Suit.CLUBS)

    def test_decide_discard_keeps_meld_cards(self):
        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),  # Part of set
                Card(Rank.KING, Suit.DIAMONDS),
            ]
        )
        discard = ai.decide_discard(hand)
        # Should discard King, not break the set
        assert discard == Card(Rank.KING, Suit.DIAMONDS)

    def test_should_knock_when_able(self):
        # Use "always" knock strategy to test basic knock behavior
        ai = BasicAI(config=make_test_config(knock_strategy="always"))
        # Hand with 10 or less deadwood
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),  # 2 deadwood
            ]
        )
        assert ai.should_knock(hand)

    def test_should_not_knock_when_high_deadwood(self):
        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.KING, Suit.SPADES),
                Card(Rank.QUEEN, Suit.HEARTS),
            ]
        )  # 20 deadwood
        assert not ai.should_knock(hand)

    def test_make_turn_decision(self):
        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
            ]
        )
        drawn = Card(Rank.KING, Suit.DIAMONDS)  # Already in hand conceptually

        discard, should_knock = ai.make_turn_decision(hand, None, drawn)

        assert discard in hand
        # With a set of aces and one king, deadwood is 10 - can knock
        assert isinstance(should_knock, bool)

    def test_never_pickup_and_immediately_discard(self):
        """Regression test for bug: AI picking up card and immediately discarding it.

        This bug occurred when decide_draw and decide_discard were not coordinated.
        decide_draw would think a card helps, but decide_discard would choose to
        discard that same card, wasting the turn and creating infinite loops.
        """
        ai = BasicAI()

        # Test many random hands to ensure the bug doesn't occur
        import random

        random.seed(42)

        for _ in range(100):
            # Generate random hand
            all_cards = [Card(rank, suit) for rank in Rank for suit in Suit]
            random.shuffle(all_cards)

            hand_cards = all_cards[:10]
            discard_top = all_cards[10]

            hand = Hand(hand_cards)

            # If AI decides to pick up from discard...
            choice = ai.decide_draw(hand, discard_top)
            if choice == DrawChoice.DISCARD:
                # Simulate picking it up
                test_hand = Hand(list(hand) + [discard_top])

                # AI should NEVER discard the card it just picked up
                discard = ai.decide_discard(test_hand)
                assert discard != discard_top, (
                    f"AI picked up {discard_top} and immediately discarded it! "
                    f"This wastes the turn and can create infinite loops."
                )


class TestContextAwareAIKnock:
    """Tests for ContextAwareAI context-aware knock decisions."""

    def _make_context(
        self,
        deck_remaining: int = 30,
        my_score: int = 0,
        opponent_score: int = 0,
        target_score: int = 100,
    ) -> GameContext:
        """Helper to create a GameContext for testing."""
        deck_position_pct = 1.0 - (deck_remaining / 31.0)
        return GameContext(
            deck_remaining=deck_remaining,
            deck_position_pct=deck_position_pct,
            my_score=my_score,
            opponent_score=opponent_score,
            target_score=target_score,
        )

    def test_always_knock_with_gin(self):
        """Should always knock with gin (0 deadwood)."""
        ai = ContextAwareAI()
        # Hand with all cards in melds - gin
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.DIAMONDS),
                Card(Rank.SIX, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.DIAMONDS),
            ]
        )
        context = self._make_context()
        assert ai.should_knock(hand, context) is True

    def test_always_knock_when_deck_nearly_empty(self):
        """Should always knock when deck has ≤4 cards (avoid draw)."""
        ai = ContextAwareAI()
        # Hand with 8 deadwood (knocking would be marginal normally)
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.SPADES),  # 8 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )
        context = self._make_context(deck_remaining=3)
        assert ai.should_knock(hand, context) is True

    def test_always_knock_for_game_winning(self):
        """Should always knock if it wins the game."""
        ai = ContextAwareAI()
        # Hand with 5 deadwood → 5 points if we knock
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.SPADES),  # 5 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )
        # Score is 95, knock would give 5 points → win
        context = self._make_context(my_score=95, target_score=100)
        assert ai.should_knock(hand, context) is True

    def test_deck_urgency_increases_knock_score(self):
        """Late game should increase knock score via urgency modifier."""
        ai = ContextAwareAI()
        # Hand with marginal deadwood (8) - above expanded gin pursuit threshold
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.SPADES),  # 8 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )

        # Mid game context (past early knock phase)
        mid_context = self._make_context(deck_remaining=18)
        mid_score = ai._calculate_knock_score(hand, mid_context)

        # Late game context (deck running low)
        late_context = self._make_context(deck_remaining=8)
        late_score = ai._calculate_knock_score(hand, late_context)

        # Late game should have higher knock score due to urgency
        assert late_score > mid_score

    def test_trailing_score_increases_aggressiveness(self):
        """When trailing significantly, should knock more aggressively."""
        ai = ContextAwareAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.SPADES),  # 7 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )

        # Even score
        even_context = self._make_context(my_score=50, opponent_score=50)
        even_score = ai._calculate_knock_score(hand, even_context)

        # Trailing significantly
        trailing_context = self._make_context(my_score=20, opponent_score=70)
        trailing_score = ai._calculate_knock_score(hand, trailing_context)

        # Trailing should have higher knock score
        assert trailing_score > even_score

    def test_leading_score_decreases_aggressiveness(self):
        """When leading significantly, should be more selective with knocking."""
        ai = ContextAwareAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.SPADES),  # 7 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )

        # Even score
        even_context = self._make_context(my_score=50, opponent_score=50)
        even_score = ai._calculate_knock_score(hand, even_context)

        # Leading significantly
        leading_context = self._make_context(my_score=80, opponent_score=30)
        leading_score = ai._calculate_knock_score(hand, leading_context)

        # Leading should have lower knock score (more selective)
        assert leading_score < even_score

    def test_opponent_weak_increases_knock_score(self):
        """When opponent estimated weak, should be more willing to knock."""
        ai = ContextAwareAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.SPADES),  # 8 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )

        # Fresh opponent (estimated ~35 deadwood)
        fresh_context = self._make_context(deck_remaining=30)
        fresh_score = ai._calculate_knock_score(hand, fresh_context)

        # Opponent has made no pickups - estimated high deadwood (weak)
        # The opponent model starts fresh with high estimated deadwood
        assert fresh_score > 0.3  # Should be willing to knock

    def test_fallback_to_basic_ai_without_context(self):
        """Without context, should fall back to BasicAI behavior."""
        # Use "always" knock strategy to test fallback knocks with any deadwood ≤10
        ai = ContextAwareAI(config=make_test_config(knock_strategy="always"))
        # Hand with 5 deadwood - BasicAI with "always" strategy should knock
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.SPADES),  # 5 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )
        # No context provided - falls back to BasicAI "always" strategy
        assert ai.should_knock(hand) is True

    def test_no_knock_when_cannot_knock(self):
        """Should not knock when deadwood > 10."""
        ai = ContextAwareAI()
        hand = Hand(
            [
                Card(Rank.KING, Suit.SPADES),
                Card(Rank.QUEEN, Suit.HEARTS),
            ]
        )  # 20 deadwood
        context = self._make_context()
        assert ai.should_knock(hand, context) is False


class TestOpponentEstimation:
    """Tests for opponent deadwood and threat estimation."""

    def _make_context(self, deck_remaining: int = 20) -> GameContext:
        """Helper to create a GameContext."""
        deck_position_pct = 1.0 - (deck_remaining / 31.0)
        return GameContext(
            deck_remaining=deck_remaining,
            deck_position_pct=deck_position_pct,
            my_score=0,
            opponent_score=0,
        )

    def test_estimate_deadwood_decreases_with_pickups(self):
        """Opponent pickups should decrease estimated deadwood."""
        model = OpponentModel()
        context = self._make_context()

        initial_estimate = model.estimate_deadwood(context)

        # Simulate opponent picking up cards
        model.record_pickup(Card(Rank.FIVE, Suit.HEARTS))
        model.record_pickup(Card(Rank.SIX, Suit.HEARTS))

        pickup_estimate = model.estimate_deadwood(context)

        # More pickups = lower estimated deadwood (building melds)
        assert pickup_estimate < initial_estimate

    def test_estimate_deadwood_decreases_with_game_progress(self):
        """Estimated deadwood should decrease as game progresses."""
        model = OpponentModel()

        early_context = self._make_context(deck_remaining=28)
        late_context = self._make_context(deck_remaining=8)

        early_estimate = model.estimate_deadwood(early_context)
        late_estimate = model.estimate_deadwood(late_context)

        # Later in game = lower expected deadwood
        assert late_estimate < early_estimate

    def test_threat_level_increases_with_pickups(self):
        """Opponent pickups should increase threat level."""
        model = OpponentModel()
        context = self._make_context()

        initial_threat = model.estimate_threat_level(context)

        # Simulate active opponent picking up cards (building melds)
        model.record_pickup(Card(Rank.FIVE, Suit.HEARTS))
        model.record_pickup(Card(Rank.SIX, Suit.HEARTS))
        model.record_pickup(Card(Rank.SEVEN, Suit.HEARTS))

        active_threat = model.estimate_threat_level(context)

        # Active opponent = higher threat
        assert active_threat > initial_threat

    def test_threat_level_capped_at_one(self):
        """Threat level should never exceed 1.0."""
        model = OpponentModel()
        context = self._make_context(deck_remaining=2)  # Very late game

        # Simulate very active opponent
        for i in range(10):
            model.record_pickup(Card(Rank(i % 13 + 1), Suit.HEARTS))

        threat = model.estimate_threat_level(context)
        assert threat <= 1.0

    def test_high_card_discards_lower_estimated_deadwood(self):
        """Discarding face cards suggests opponent has melds to hold."""
        model = OpponentModel()
        context = self._make_context()

        initial_estimate = model.estimate_deadwood(context)

        # Opponent discards high cards (suggests they have melds)
        model.record_discard(Card(Rank.KING, Suit.SPADES))
        model.record_discard(Card(Rank.QUEEN, Suit.HEARTS))
        model.record_discard(Card(Rank.JACK, Suit.CLUBS))

        after_discards = model.estimate_deadwood(context)

        # High card discards = lower estimated deadwood
        assert after_discards < initial_estimate


class TestReasoningMethods:
    """Tests for AI *_with_reasoning() methods."""

    def test_basic_ai_draw_with_reasoning_deck_empty_discard(self):
        """BasicAI should return proper reasoning when discard pile is empty."""
        from gin_rummy.ai import DrawChoice, DrawReasoning

        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.THREE, Suit.HEARTS),
            ]
        )
        reasoning = ai.decide_draw_with_reasoning(hand, None)

        assert isinstance(reasoning, DrawReasoning)
        assert reasoning.choice == DrawChoice.DECK
        assert "empty" in reasoning.reasoning.lower()
        assert len(reasoning.factors) > 0

    def test_basic_ai_draw_with_reasoning_takes_helpful_card(self):
        """BasicAI should explain why it takes a helpful card."""
        from gin_rummy.ai import DrawChoice, DrawReasoning

        ai = BasicAI()
        # Hand with two aces - third ace would form a set
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.KING, Suit.CLUBS),
            ]
        )
        discard = Card(Rank.ACE, Suit.CLUBS)
        reasoning = ai.decide_draw_with_reasoning(hand, discard)

        assert isinstance(reasoning, DrawReasoning)
        assert reasoning.choice == DrawChoice.DISCARD
        assert str(discard) in reasoning.reasoning or "DISCARD" in reasoning.reasoning

    def test_basic_ai_discard_with_reasoning(self):
        """BasicAI should provide discard reasoning with options."""
        from gin_rummy.ai import DiscardReasoning

        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.TWO, Suit.HEARTS),
                Card(Rank.KING, Suit.CLUBS),
            ]
        )
        reasoning = ai.decide_discard_with_reasoning(hand)

        assert isinstance(reasoning, DiscardReasoning)
        assert reasoning.card in list(hand)
        assert len(reasoning.reasoning) > 0
        assert len(reasoning.factors) > 0
        assert len(reasoning.options_considered) > 0

    def test_basic_ai_knock_with_reasoning_gin(self):
        """BasicAI should always knock with gin and explain why."""
        from gin_rummy.ai import KnockReasoning

        ai = BasicAI()
        # Hand with all cards in melds - gin
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.DIAMONDS),
                Card(Rank.SIX, Suit.DIAMONDS),
                Card(Rank.SEVEN, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.DIAMONDS),
            ]
        )
        reasoning = ai.should_knock_with_reasoning(hand)

        assert isinstance(reasoning, KnockReasoning)
        assert reasoning.should_knock is True
        assert "gin" in reasoning.reasoning.lower()

    def test_basic_ai_knock_with_reasoning_cannot_knock(self):
        """BasicAI should explain when it can't knock due to high deadwood."""
        from gin_rummy.ai import KnockReasoning

        ai = BasicAI()
        hand = Hand(
            [
                Card(Rank.KING, Suit.SPADES),
                Card(Rank.QUEEN, Suit.HEARTS),
            ]
        )  # 20 deadwood
        reasoning = ai.should_knock_with_reasoning(hand)

        assert isinstance(reasoning, KnockReasoning)
        assert reasoning.should_knock is False
        assert "20" in reasoning.reasoning or "> 10" in reasoning.reasoning

    def test_context_aware_ai_knock_with_reasoning_includes_score(self):
        """ContextAwareAI should include knock score in reasoning."""
        from gin_rummy.ai import KnockReasoning
        from gin_rummy.context import GameContext

        ai = ContextAwareAI()
        # Hand with 5 deadwood
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.SPADES),  # 5 deadwood
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )
        context = GameContext(
            deck_remaining=20,
            deck_position_pct=0.35,
            my_score=0,
            opponent_score=0,
            target_score=100,
        )
        reasoning = ai.should_knock_with_reasoning(hand, context)

        assert isinstance(reasoning, KnockReasoning)
        # Should have a numeric score
        assert reasoning.score is not None
        # Should have multiple factors
        assert len(reasoning.factors) >= 2

    def test_context_aware_ai_discard_with_reasoning_includes_flags(self):
        """ContextAwareAI should include safety flags in discard reasoning."""
        from gin_rummy.ai import DiscardReasoning

        ai = ContextAwareAI()
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
            ]
        )
        reasoning = ai.decide_discard_with_reasoning(hand)

        assert isinstance(reasoning, DiscardReasoning)
        assert reasoning.card in list(hand)
        # Should have factors explaining the decision
        assert len(reasoning.factors) > 0


class TestSharedInterface:
    """Every AI honours the BasicAI interface, so callers never check the class (AUDIT §2.3)."""

    import inspect as _inspect

    ALL_TYPES = ("basic", "context", "statistical", "montecarlo")

    def _make(self, kind):
        from gin_rummy.ai import make_ai
        from tests.helpers import make_mc_config

        return make_ai(kind, make_mc_config() if kind == "montecarlo" else None)

    @pytest.mark.parametrize("kind", ALL_TYPES)
    def test_uniform_signatures(self, kind):
        ai = self._make(kind)
        params = lambda f: list(self._inspect.signature(f).parameters)  # noqa: E731
        assert params(ai.decide_draw) == ["hand", "discard_top", "context"]
        assert params(ai.decide_discard) == ["hand", "context"]
        assert params(ai.should_knock) == ["hand", "context", "pending_discard"]
        assert params(ai.decide_draw_with_reasoning) == ["hand", "discard_top", "context"]
        assert params(ai.decide_discard_with_reasoning) == ["hand", "context"]
        assert params(ai.should_knock_with_reasoning) == ["hand", "context", "pending_discard"]

    @pytest.mark.parametrize("kind", ALL_TYPES)
    def test_tracking_hooks_exist_and_are_safe(self, kind):
        ai = self._make(kind)
        card = Card(Rank.SEVEN, Suit.HEARTS)
        ai.record_opponent_pickup(card)
        ai.record_opponent_discard(card)
        assert ai.opponent_model.total_discards == 1
        ai.reset_for_new_hand()
        assert ai.opponent_model.total_discards == 0
        assert not hasattr(ai, "update_context")  # decisions take the context explicitly

    def test_needs_context_flags(self):
        from gin_rummy.ai import MonteCarloAI, StatisticalAI

        assert BasicAI.needs_context is False
        assert StatisticalAI.needs_context is False
        assert ContextAwareAI.needs_context is True
        assert MonteCarloAI.needs_context is True

    def test_basic_ai_ignores_context_and_pending_discard(self):
        ai = BasicAI(make_test_config())
        hand = Hand([Card(Rank.ACE, Suit.SPADES), Card(Rank.TWO, Suit.HEARTS)])
        assert ai.should_knock(hand) == ai.should_knock(hand, None, pending_discard=Card(Rank.KING, Suit.CLUBS))
        assert ai.decide_discard(hand) == ai.decide_discard(hand, None)


class TestFactory:
    def test_make_ai_types(self):
        from gin_rummy.ai import AI_TYPES, MonteCarloAI, StatisticalAI, make_ai
        from tests.helpers import make_mc_config

        assert set(AI_TYPES) == {"basic", "context", "statistical", "montecarlo", "learning"}
        assert type(make_ai("basic")) is BasicAI
        assert type(make_ai("context")) is ContextAwareAI
        assert type(make_ai("statistical")) is StatisticalAI
        mc = make_ai("montecarlo", make_mc_config())
        assert type(mc) is MonteCarloAI
        mc.shutdown()

    def test_unknown_type_raises(self):
        from gin_rummy.ai import make_ai

        with pytest.raises(ValueError, match="Unknown AI type"):
            make_ai("chess")

    def test_difficulty_map_covers_web_levels(self):
        from gin_rummy.ai import AI_TYPES, DIFFICULTY_TO_AI

        assert set(DIFFICULTY_TO_AI) == {"easy", "medium", "hard"}
        assert set(DIFFICULTY_TO_AI.values()) <= set(AI_TYPES)


class TestKnockThresholdFromContext:
    """B9: the knock threshold in effect (Oklahoma) comes from the context, not a hard-coded 10."""

    SEVEN_DEADWOOD = "AS 2S 3S 4H 5H 6H 7C 8C 9C 7D"

    @pytest.mark.parametrize("kind", ["basic", "context", "statistical"])
    def test_context_threshold_blocks_knock(self, kind):
        from dataclasses import replace

        from gin_rummy.ai import make_ai
        from tests.helpers import hand, make_context

        h = hand(self.SEVEN_DEADWOOD)
        assert h.deadwood_total == 7
        cfg = make_test_config("always")  # config threshold is 10 -> would knock
        ai = make_ai(kind, cfg)
        assert ai.should_knock(h, make_context(h)) is True
        assert ai.should_knock(h) is True

        oklahoma = replace(make_context(h), knock_threshold=5)
        ai = make_ai(kind, cfg)
        assert ai.should_knock(h, oklahoma) is False
        ai = make_ai(kind, cfg)
        assert ai.should_knock_with_reasoning(h, oklahoma).should_knock is False

    def test_make_turn_decision_respects_context_threshold(self):
        from dataclasses import replace

        from tests.helpers import card, hand, make_context

        eleven = hand(self.SEVEN_DEADWOOD + " KD")
        ai = BasicAI(make_test_config("always"))
        _, knock = ai.make_turn_decision(eleven, None, card("KD"), make_context(eleven))
        assert knock is True
        oklahoma = replace(make_context(eleven), knock_threshold=5)
        _, knock = ai.make_turn_decision(eleven, None, card("KD"), oklahoma)
        assert knock is False
