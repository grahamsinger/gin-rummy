"""Tests for Monte Carlo AI module."""

import random

import pytest

from gin_rummy.ai import BasicAI, DrawChoice, MonteCarloAI
from gin_rummy.ai.mc.rollout import (
    ALL_CARDS,
    RolloutResult,
    evaluate_terminal,
    rollout,
    score_knock,
)
from gin_rummy.ai.mc.thinking import DrawThinking, KnockThinking, MCThinking
from gin_rummy.config import Config, MonteCarloAIConfig
from gin_rummy.models import Card, Hand, Rank, Suit
from tests.helpers import cards, make_context
from tests.helpers import make_mc_config as make_test_config


class TestScoreKnock:
    """Tests for the score_knock function."""

    def test_gin_scores_bonus_plus_defender_deadwood(self):
        """Gin should give gin_bonus + defender's deadwood."""
        knocker_hand = [
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
        defender_hand = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.QUEEN, Suit.HEARTS),
        ]
        points, is_gin, is_undercut = score_knock(knocker_hand, defender_hand)
        assert is_gin is True
        assert is_undercut is False
        assert points == 25 + 20  # gin_bonus + K(10) + Q(10)

    def test_regular_knock_scores_difference(self):
        """Regular knock should score the deadwood difference."""
        knocker_hand = [
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
        defender_hand = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.QUEEN, Suit.HEARTS),
            Card(Rank.JACK, Suit.DIAMONDS),
        ]
        points, is_gin, is_undercut = score_knock(knocker_hand, defender_hand)
        assert is_gin is False
        assert is_undercut is False
        assert points > 0  # Defender has more deadwood

    def test_undercut_returns_negative(self):
        """Undercut should return negative points for the knocker."""
        knocker_hand = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.EIGHT, Suit.SPADES),  # 8 deadwood
            Card(Rank.TWO, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.DIAMONDS),
            Card(Rank.FOUR, Suit.DIAMONDS),
            Card(Rank.FIVE, Suit.CLUBS),
            Card(Rank.SIX, Suit.CLUBS),
            Card(Rank.SEVEN, Suit.CLUBS),
        ]
        # Defender has lower deadwood after layoff
        defender_hand = [
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.THREE, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.FOUR, Suit.HEARTS),
            Card(Rank.FOUR, Suit.CLUBS),
            Card(Rank.ACE, Suit.DIAMONDS),  # 1 deadwood
        ]
        points, is_gin, is_undercut = score_knock(knocker_hand, defender_hand)
        assert is_gin is False
        assert is_undercut is True
        assert points < 0


class TestRollout:
    """Tests for the rollout function."""

    def test_rollout_terminates(self):
        """Rollout should always terminate within max_turns."""
        random.seed(42)
        ai = BasicAI()

        for _ in range(20):
            all_cards = list(ALL_CARDS)
            random.shuffle(all_cards)
            my_hand = all_cards[:10]
            opp_hand = all_cards[10:20]
            deck = all_cards[20:40]
            discard = all_cards[40:42]

            result = rollout(
                list(my_hand),
                list(opp_hand),
                list(deck),
                list(discard),
                True,
                ai,
                max_turns=8,
            )
            assert isinstance(result, RolloutResult)

    def test_rollout_returns_valid_result(self):
        """Rollout result should have sensible values."""
        random.seed(42)
        ai = BasicAI()

        all_cards = list(ALL_CARDS)
        random.shuffle(all_cards)
        my_hand = all_cards[:10]
        opp_hand = all_cards[10:20]
        deck = all_cards[20:40]
        discard = all_cards[40:42]

        result = rollout(
            list(my_hand),
            list(opp_hand),
            list(deck),
            list(discard),
            True,
            ai,
            max_turns=8,
        )
        assert isinstance(result.my_points, int)
        assert isinstance(result.is_draw, bool)
        assert isinstance(result.i_knocked, bool)

    def test_rollout_with_empty_deck_returns_draw(self):
        """Rollout should return draw when deck is nearly empty."""
        ai = BasicAI()
        all_cards = list(ALL_CARDS)
        random.seed(42)
        random.shuffle(all_cards)
        my_hand = all_cards[:10]
        opp_hand = all_cards[10:20]
        deck = all_cards[20:22]  # Only 2 cards - will trigger draw
        discard = all_cards[22:30]

        result = rollout(
            list(my_hand),
            list(opp_hand),
            list(deck),
            list(discard),
            True,
            ai,
            max_turns=8,
        )
        assert result.is_draw is True


class TestMonteCarloAI:
    """Tests for the MonteCarloAI class."""

    def test_inherits_context_aware(self):
        """MonteCarloAI should be an instance of ContextAwareAI."""
        from gin_rummy.ai.context_aware import ContextAwareAI

        ai = MonteCarloAI(config=make_test_config())
        assert isinstance(ai, ContextAwareAI)
        assert isinstance(ai, BasicAI)

    def test_decide_draw_returns_valid_choice(self):
        """Draw decision should return DECK or DISCARD."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
            ]
        )
        discard_top = Card(Rank.TWO, Suit.DIAMONDS)
        context = make_context(hand)
        choice = ai.decide_draw(hand, discard_top, context)
        assert choice in (DrawChoice.DECK, DrawChoice.DISCARD)

    def test_decide_draw_with_no_discard(self):
        """Should return DECK when discard pile is empty."""
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand([Card(Rank.ACE, Suit.SPADES), Card(Rank.TWO, Suit.HEARTS)])
        assert ai.decide_draw(hand, None) == DrawChoice.DECK

    def test_decide_discard_returns_card_in_hand(self):
        """Discard decision should return a card from the hand."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.SIX, Suit.CLUBS),  # 11 cards after draw
            ]
        )
        context = make_context(hand)
        discard = ai.decide_discard(hand, context)
        assert discard in list(hand)

    def test_should_knock_returns_bool(self):
        """Knock decision should return a boolean."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
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
        context = make_context(hand)
        result = ai.should_knock(hand, context)
        assert isinstance(result, bool)

    def test_always_knocks_with_gin(self):
        """Should always knock with 0 deadwood (gin)."""
        ai = MonteCarloAI(config=make_test_config())
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
        assert ai.should_knock(hand) is True

    def test_stores_mc_thinking_data(self):
        """MonteCarloAI should store thinking data for UI."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
            ]
        )
        discard_top = Card(Rank.TWO, Suit.DIAMONDS)
        context = make_context(hand)

        ai.decide_draw(hand, discard_top, context)

        assert ai.last_mc_thinking is not None
        draw_data = ai.last_mc_thinking.draw
        assert draw_data is not None
        assert isinstance(draw_data.deck_avg_points, float)
        assert isinstance(draw_data.discard_avg_points, float)
        assert hasattr(draw_data, "choice")

    def test_reasoning_methods_return_correct_types(self):
        """Reasoning methods should return proper reasoning objects."""
        from gin_rummy.ai.types import DiscardReasoning, DrawReasoning, KnockReasoning

        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
            ]
        )
        discard_top = Card(Rank.TWO, Suit.DIAMONDS)
        context = make_context(hand)

        draw_r = ai.decide_draw_with_reasoning(hand, discard_top, context)
        assert isinstance(draw_r, DrawReasoning)
        assert draw_r.choice in (DrawChoice.DECK, DrawChoice.DISCARD)

        # 11-card hand for discard
        hand_11 = Hand(list(hand) + [discard_top])
        discard_r = ai.decide_discard_with_reasoning(hand_11, context)
        assert isinstance(discard_r, DiscardReasoning)
        assert discard_r.card in list(hand_11)

        knock_r = ai.should_knock_with_reasoning(hand, context)
        assert isinstance(knock_r, KnockReasoning)
        assert isinstance(knock_r.should_knock, bool)


class TestInformationSetSampling:
    """Tests for _get_known_and_unknown and _sample_game_state."""

    def test_known_unknown_partition(self):
        """Known + unknown should cover all 52 cards with no overlap."""
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.TWO, Suit.HEARTS),
                Card(Rank.THREE, Suit.CLUBS),
            ]
        )
        context = make_context(hand)
        known, unknown = ai._get_known_and_unknown(hand, context)
        assert len(known) + len(unknown) == 52
        assert not known.intersection(set(unknown))

    def test_sample_returns_correct_sizes(self):
        """Sampled state should have correct hand/deck sizes."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
        my_hand = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
        ]
        unknown = [c for c in ALL_CARDS if c not in my_hand]

        opp_hand, deck, discard = ai._sample_game_state(my_hand, unknown, set(), 20, [])
        assert len(opp_hand) == 10
        assert len(deck) == len(unknown) - 10


class TestEvaluateTerminal:
    """Tests for the evaluate_terminal function."""

    def test_better_hand_scores_positive(self):
        """Lower deadwood hand should get a positive score."""
        # Good hand: 3 aces (meld) + low deadwood
        my_hand = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.TWO, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.DIAMONDS),
            Card(Rank.FOUR, Suit.DIAMONDS),
            Card(Rank.FIVE, Suit.DIAMONDS),
            Card(Rank.SIX, Suit.DIAMONDS),
            Card(Rank.SEVEN, Suit.DIAMONDS),
            Card(Rank.TWO, Suit.SPADES),  # 2 deadwood
        ]
        # Bad hand: high deadwood
        opp_hand = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.QUEEN, Suit.HEARTS),
            Card(Rank.JACK, Suit.CLUBS),
            Card(Rank.TEN, Suit.DIAMONDS),
            Card(Rank.NINE, Suit.SPADES),
            Card(Rank.EIGHT, Suit.HEARTS),
            Card(Rank.SEVEN, Suit.CLUBS),
            Card(Rank.SIX, Suit.SPADES),
            Card(Rank.FIVE, Suit.HEARTS),
            Card(Rank.FOUR, Suit.CLUBS),
        ]
        score = evaluate_terminal(my_hand, opp_hand)
        assert score > 0

    def test_worse_hand_scores_negative(self):
        """Higher deadwood hand should get a negative score."""
        my_hand = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.QUEEN, Suit.HEARTS),
            Card(Rank.JACK, Suit.CLUBS),
            Card(Rank.TEN, Suit.DIAMONDS),
            Card(Rank.NINE, Suit.SPADES),
            Card(Rank.EIGHT, Suit.HEARTS),
            Card(Rank.SEVEN, Suit.CLUBS),
            Card(Rank.SIX, Suit.SPADES),
            Card(Rank.FIVE, Suit.HEARTS),
            Card(Rank.FOUR, Suit.CLUBS),
        ]
        opp_hand = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.TWO, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.DIAMONDS),
            Card(Rank.FOUR, Suit.DIAMONDS),
            Card(Rank.FIVE, Suit.DIAMONDS),
            Card(Rank.SIX, Suit.DIAMONDS),
            Card(Rank.SEVEN, Suit.DIAMONDS),
            Card(Rank.TWO, Suit.SPADES),
        ]
        score = evaluate_terminal(my_hand, opp_hand)
        assert score < 0

    def test_meld_bonus_contributes(self):
        """Hands with more melds should score higher than raw deadwood suggests."""
        # Hand with melds but same deadwood as a hand without
        hand_with_melds = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.KING, Suit.DIAMONDS),  # 10 deadwood
        ]
        hand_no_melds = [
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.FOUR, Suit.HEARTS),
            Card(Rank.SIX, Suit.CLUBS),
            Card(Rank.FIVE, Suit.DIAMONDS),  # Could be ~17 deadwood
        ]
        # Score from perspective of hand_with_melds
        score = evaluate_terminal(hand_with_melds, hand_no_melds)
        # The meld bonus should make this more positive than just deadwood diff
        assert score > 0

    def test_equal_hands_near_zero(self):
        """Identical hand structures should score near zero."""
        hand = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.KING, Suit.DIAMONDS),
        ]
        # Same structure, different suits
        other = [
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.KING, Suit.HEARTS),
        ]
        score = evaluate_terminal(hand, other)
        # Should be close to zero (same meld count, similar deadwood)
        assert abs(score) < 15  # Allow some difference from deadwood values


class TestConfidenceThresholdFallback:
    """Tests for confidence threshold fallback behavior."""

    def test_draw_fallback_data_in_thinking(self):
        """Draw thinking should include fallback and advantage data."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
            ]
        )
        discard_top = Card(Rank.TWO, Suit.DIAMONDS)
        context = make_context(hand)

        ai.decide_draw(hand, discard_top, context)

        assert ai.last_mc_thinking is not None
        draw_data = ai.last_mc_thinking.draw
        assert draw_data is not None
        assert isinstance(draw_data.fallback, bool)
        assert isinstance(draw_data.advantage, float)

    def test_knock_fallback_data_in_thinking(self):
        """Knock thinking should include fallback and advantage data."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
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
        context = make_context(hand)

        ai.should_knock(hand, context)

        assert ai.last_mc_thinking is not None
        knock_data = ai.last_mc_thinking.knock
        assert knock_data is not None
        assert isinstance(knock_data.fallback, bool)
        assert isinstance(knock_data.advantage, float)

    def test_discard_fallback_data_in_thinking(self):
        """Discard thinking should include fallback data."""
        random.seed(42)
        ai = MonteCarloAI(config=make_test_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.SIX, Suit.CLUBS),
            ]
        )
        context = make_context(hand)

        ai.decide_discard(hand, context)

        assert ai.last_mc_thinking is not None
        discard_data = ai.last_mc_thinking.discard
        assert discard_data is not None
        assert isinstance(discard_data.fallback, bool)

    def test_rollout_ai_uses_conservative_knock(self):
        """Rollout AI should use conservative knock strategy."""
        ai = MonteCarloAI(config=make_test_config())
        assert ai._rollout_ai.knock_strategy == "conservative"
        assert ai._rollout_ai.conservative_knock_threshold == 3


class TestParallelizationConfig:
    """Tests for multiprocessing and sample strategy configuration."""

    def test_max_workers_auto(self):
        """max_workers=0 should auto-compute to cpu_count - 1."""
        import os

        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(max_workers=0)
        ai = MonteCarloAI(config=config)
        expected = max(1, (os.cpu_count() or 2) - 1)
        assert ai._max_workers == expected

    def test_max_workers_explicit(self):
        """Explicit max_workers should be stored directly."""
        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(max_workers=4)
        ai = MonteCarloAI(config=config)
        assert ai._max_workers == 4

    def test_max_workers_minimum_one(self):
        """max_workers should never go below 1."""
        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(max_workers=-1)
        ai = MonteCarloAI(config=config)
        assert ai._max_workers == 1

    def test_sample_strategy_paired(self):
        """sample_strategy='paired' should be stored correctly."""
        config = make_test_config()
        ai = MonteCarloAI(config=config)
        assert ai._sample_strategy == "paired"

    def test_sample_strategy_independent(self):
        """sample_strategy='independent' should be stored correctly."""
        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(
            sample_strategy="independent",
            max_workers=1,
        )
        ai = MonteCarloAI(config=config)
        assert ai._sample_strategy == "independent"

    def test_sequential_no_pool(self):
        """max_workers=1 should not create a process pool."""
        config = make_test_config()
        ai = MonteCarloAI(config=config)
        assert ai._get_pool() is None


class TestPairedSamples:
    """Tests for paired sample mode producing valid results."""

    def test_paired_draw_produces_result(self):
        """MC draw should work in paired sample mode."""
        random.seed(42)
        config = make_test_config()
        ai = MonteCarloAI(config=config)
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
            ]
        )
        discard_top = Card(Rank.TWO, Suit.DIAMONDS)
        context = make_context(hand)
        choice = ai.decide_draw(hand, discard_top, context)
        assert choice in (DrawChoice.DECK, DrawChoice.DISCARD)

    def test_paired_discard_produces_result(self):
        """MC discard should work in paired sample mode."""
        random.seed(42)
        config = make_test_config()
        ai = MonteCarloAI(config=config)
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.SIX, Suit.CLUBS),
            ]
        )
        context = make_context(hand)
        discard = ai.decide_discard(hand, context)
        assert discard in list(hand)

    def test_paired_knock_produces_result(self):
        """MC knock should work in paired sample mode."""
        random.seed(42)
        config = make_test_config()
        ai = MonteCarloAI(config=config)
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.SPADES),
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )
        context = make_context(hand)
        result = ai.should_knock(hand, context)
        assert isinstance(result, bool)


class TestIndependentSamples:
    """Tests for independent sample mode producing valid results."""

    def _make_independent_config(self) -> Config:
        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(
            draw_simulations=10,
            discard_simulations=10,
            knock_simulations=10,
            max_rollout_turns=4,
            min_unknown_for_simulation=3,
            rollout_knock_strategy="conservative",
            rollout_conservative_threshold=3,
            draw_min_advantage=1.5,
            discard_min_advantage=1.0,
            knock_min_advantage=2.0,
            max_workers=1,
            sample_strategy="independent",
        )
        return config

    def test_independent_draw_produces_result(self):
        """MC draw should work in independent sample mode."""
        random.seed(42)
        ai = MonteCarloAI(config=self._make_independent_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
            ]
        )
        discard_top = Card(Rank.TWO, Suit.DIAMONDS)
        context = make_context(hand)
        choice = ai.decide_draw(hand, discard_top, context)
        assert choice in (DrawChoice.DECK, DrawChoice.DISCARD)

    def test_independent_discard_produces_result(self):
        """MC discard should work in independent sample mode."""
        random.seed(42)
        ai = MonteCarloAI(config=self._make_independent_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.SIX, Suit.CLUBS),
            ]
        )
        context = make_context(hand)
        discard = ai.decide_discard(hand, context)
        assert discard in list(hand)

    def test_independent_knock_produces_result(self):
        """MC knock should work in independent sample mode."""
        random.seed(42)
        ai = MonteCarloAI(config=self._make_independent_config())
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.SPADES),
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )
        context = make_context(hand)
        result = ai.should_knock(hand, context)
        assert isinstance(result, bool)


class TestParallelMode:
    """Tests for multiprocessing mode."""

    def test_parallel_mode_draw(self):
        """MC draw should work with max_workers=2."""
        import os

        if (os.cpu_count() or 1) < 2:
            pytest.skip("Need at least 2 CPUs for parallel test")

        random.seed(42)
        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(
            draw_simulations=10,
            discard_simulations=10,
            knock_simulations=10,
            max_rollout_turns=4,
            min_unknown_for_simulation=3,
            max_workers=2,
            sample_strategy="paired",
        )
        ai = MonteCarloAI(config=config)
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
            ]
        )
        discard_top = Card(Rank.TWO, Suit.DIAMONDS)
        context = make_context(hand)
        try:
            choice = ai.decide_draw(hand, discard_top, context)
            assert choice in (DrawChoice.DECK, DrawChoice.DISCARD)
        finally:
            ai.shutdown()

    def test_parallel_mode_discard(self):
        """MC discard should work with max_workers=2."""
        import os

        if (os.cpu_count() or 1) < 2:
            pytest.skip("Need at least 2 CPUs for parallel test")

        random.seed(42)
        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(
            draw_simulations=10,
            discard_simulations=10,
            knock_simulations=10,
            max_rollout_turns=4,
            min_unknown_for_simulation=3,
            max_workers=2,
            sample_strategy="paired",
        )
        ai = MonteCarloAI(config=config)
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.KING, Suit.DIAMONDS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.SPADES),
                Card(Rank.TEN, Suit.CLUBS),
                Card(Rank.NINE, Suit.DIAMONDS),
                Card(Rank.EIGHT, Suit.HEARTS),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.SIX, Suit.CLUBS),
            ]
        )
        context = make_context(hand)
        try:
            discard = ai.decide_discard(hand, context)
            assert discard in list(hand)
        finally:
            ai.shutdown()

    def test_parallel_mode_knock(self):
        """MC knock should work with max_workers=2."""
        import os

        if (os.cpu_count() or 1) < 2:
            pytest.skip("Need at least 2 CPUs for parallel test")

        random.seed(42)
        config = Config()
        config.monte_carlo_ai = MonteCarloAIConfig(
            draw_simulations=10,
            discard_simulations=10,
            knock_simulations=10,
            max_rollout_turns=4,
            min_unknown_for_simulation=3,
            max_workers=2,
            sample_strategy="paired",
        )
        ai = MonteCarloAI(config=config)
        hand = Hand(
            [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.ACE, Suit.CLUBS),
                Card(Rank.TWO, Suit.DIAMONDS),
                Card(Rank.THREE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.SPADES),
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SIX, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.CLUBS),
            ]
        )
        context = make_context(hand)
        try:
            result = ai.should_knock(hand, context)
            assert isinstance(result, bool)
        finally:
            ai.shutdown()

    def test_shutdown_cleans_pool(self):
        """shutdown() should clean up the pool."""
        config = make_test_config()
        ai = MonteCarloAI(config=config)
        ai.shutdown()
        assert ai._pool is None


def _stale_draw() -> DrawThinking:
    return DrawThinking(1.0, 99, 2.0, 99, "2D", "deck", 1.0, False)


def _stale_knock() -> KnockThinking:
    return KnockThinking(chose_knock=False, deadwood=9, knock_avg_points=1.0, continue_avg_points=2.0)


class TestThinkingReset:
    """B7: early returns must not leave the previous turn's MC numbers behind."""

    def test_early_return_clears_stale_draw_thinking(self):
        ai = MonteCarloAI(config=make_test_config())
        stale_knock = _stale_knock()
        ai.last_mc_thinking = MCThinking(draw=_stale_draw(), knock=stale_knock)
        hand = Hand([Card(Rank.ACE, Suit.SPADES), Card(Rank.TWO, Suit.HEARTS)])

        # No discard top -> early return before any simulation
        assert ai.decide_draw(hand, None, make_context(hand)) == DrawChoice.DECK
        assert ai.last_mc_thinking.draw is None
        assert ai.last_mc_thinking.knock is stale_knock  # untouched

    def test_gin_knock_keeps_its_own_reasoning(self):
        """Regression: clearing must not run after reasoning was just stored."""
        ai = MonteCarloAI(config=make_test_config())
        ai.last_mc_thinking = MCThinking(knock=_stale_knock())
        gin = Hand(cards("AS 2S 3S 4S 5S 6S 7S 8S 9S 10S"))

        assert ai.should_knock(gin, make_context(gin)) is True
        assert ai.last_mc_thinking.knock is not None and ai.last_mc_thinking.knock.reason == "gin"

    def test_late_deck_knock_keeps_its_own_reasoning(self):
        ai = MonteCarloAI(config=make_test_config())
        ai.last_mc_thinking = None
        low = Hand(cards("AS 2S 3S 4H 5H 6H 7C 8C 9C 2D"))  # 2 deadwood

        assert ai.should_knock(low, make_context(low, deck_remaining=3)) is True
        assert ai.last_mc_thinking is not None and ai.last_mc_thinking.knock is not None
        assert ai.last_mc_thinking.knock.reason == "deck_nearly_empty"

    def test_early_return_clears_stale_knock_thinking(self):
        ai = MonteCarloAI(config=make_test_config())
        ai.last_mc_thinking = MCThinking(knock=_stale_knock())
        high_deadwood = Hand([Card(Rank.KING, Suit.SPADES), Card(Rank.QUEEN, Suit.HEARTS)])

        assert ai.should_knock(high_deadwood, make_context(high_deadwood)) is False
        assert ai.last_mc_thinking.knock is None

    def test_to_dict_keeps_the_web_shape(self):
        t = MCThinking(draw=_stale_draw())
        d = t.to_dict()
        assert set(d) == {"draw", "discard", "knock"}
        assert d["discard"] is None and d["knock"] is None
        assert d["draw"]["deck_sims"] == 99 and d["draw"]["choice"] == "deck"
