"""Tests for the three MonteCarloAI upgrades (2026-07-12):

1. Weighted opponent-hand sampling
2. Defensive rollout discards
3. Joint discard+knock turn evaluation
"""

import random

from gin_rummy.ai import MonteCarloAI, BasicAI
from gin_rummy.ai.monte_carlo import _sample_state, _rollout_discard
from gin_rummy.config import Config, MonteCarloAIConfig
from gin_rummy.context import GameContext, KnownCards
from gin_rummy.models import Hand, Card, Suit, Rank
from tests.helpers import make_context, make_mc_config as make_test_config


class TestWeightedSampling:
    def test_weighted_sample_state_biases_opponent_hand(self):
        random.seed(123)
        unknown = [Card(rank, suit) for suit in Suit for rank in Rank][:30]
        likely = unknown[0]
        unlikely = unknown[1]
        weights = {likely: 8.0, unlikely: 0.05}

        likely_count = 0
        unlikely_count = 0
        n = 500
        for _ in range(n):
            opp_hand, _ = _sample_state(unknown, [], weights)
            if likely in opp_hand:
                likely_count += 1
            if unlikely in opp_hand:
                unlikely_count += 1

        # Uniform baseline would be 10/30 = ~167 of 500 for each
        assert likely_count > 300, f"high-weight card sampled only {likely_count}/{n}"
        assert unlikely_count < 60, f"low-weight card sampled {unlikely_count}/{n}"

    def test_sampled_hands_still_valid(self):
        random.seed(5)
        unknown = [Card(rank, suit) for suit in Suit for rank in Rank][:25]
        weights = {c: 0.5 + (i % 5) for i, c in enumerate(unknown)}
        opp_known = [Card(Rank.ACE, Suit.SPADES)]

        opp_hand, deck = _sample_state(unknown, opp_known, weights)
        assert len(opp_hand) == 10
        assert len(deck) == len(unknown) - 9  # 9 filled + rest to deck
        assert len(set(opp_hand) | set(deck)) == len(opp_hand) + len(deck)

    def test_build_weights_from_observations(self):
        ai = MonteCarloAI(make_test_config())

        # Opponent discarded 7H: 7D less likely, 6H/8H less likely
        ai.record_opponent_discard(Card(Rank.SEVEN, Suit.HEARTS))
        # Opponent picked up 9S twice-adjacent cards: builds inference
        ai.record_opponent_pickup(Card(Rank.NINE, Suit.SPADES))
        ai.record_opponent_pickup(Card(Rank.TEN, Suit.SPADES))

        weights = ai._build_sample_weights()
        assert weights is not None
        assert weights[Card(Rank.SEVEN, Suit.DIAMONDS)] < 1.0
        assert weights[Card(Rank.SIX, Suit.HEARTS)] < 1.0
        assert weights[Card(Rank.EIGHT, Suit.HEARTS)] < 1.0
        # 8S/JS complete the inferred 9S-10S run -> more likely held
        assert weights[Card(Rank.EIGHT, Suit.SPADES)] > 1.0
        assert weights[Card(Rank.JACK, Suit.SPADES)] > 1.0

    def test_no_weights_without_observations_or_flag(self):
        ai = MonteCarloAI(make_test_config())
        assert ai._build_sample_weights() is None  # no observations yet

        ai_off = MonteCarloAI(make_test_config(weighted_sampling=False))
        ai_off.record_opponent_discard(Card(Rank.SEVEN, Suit.HEARTS))
        assert ai_off._build_sample_weights() is None  # flag off


class TestDefensiveRollout:
    def test_defensive_discard_avoids_feeding_opponent(self):
        rollout_ai = BasicAI(make_test_config())

        # My hand: 2H 3H 4H meld + 8 near-equal junk incl. KD and KC.
        # Opponent holds KS KH: discarding either king completes their set.
        current = [
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.HEARTS),
            Card(Rank.FOUR, Suit.HEARTS),
            Card(Rank.KING, Suit.DIAMONDS),
            Card(Rank.QUEEN, Suit.CLUBS),
            Card(Rank.NINE, Suit.DIAMONDS),
            Card(Rank.SEVEN, Suit.CLUBS),
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.SIX, Suit.CLUBS),
            Card(Rank.JACK, Suit.DIAMONDS),
        ]
        other = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.FOUR, Suit.DIAMONDS),
            Card(Rank.SIX, Suit.SPADES),
            Card(Rank.EIGHT, Suit.HEARTS),
            Card(Rank.TEN, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FIVE, Suit.DIAMONDS),
            Card(Rank.NINE, Suit.CLUBS),
        ]

        greedy = _rollout_discard(current, other, rollout_ai, defensive=False)
        defensive = _rollout_discard(current, other, rollout_ai, defensive=True)

        # Greedy (deadwood-minimizing) throws the king; defensive must not
        # complete the opponent's king set when a near-equal discard exists
        assert greedy == Card(Rank.KING, Suit.DIAMONDS)
        assert defensive != Card(Rank.KING, Suit.DIAMONDS), (
            f"defensive rollout fed the opponent's king set with {defensive}"
        )

    def test_defensive_falls_back_to_greedy_when_all_feed(self):
        rollout_ai = BasicAI(make_test_config())
        # Two-card toy hand where every discard helps the other side
        current = [
            Card(Rank.KING, Suit.DIAMONDS),
            Card(Rank.QUEEN, Suit.DIAMONDS),
            Card(Rank.QUEEN, Suit.SPADES),
        ]
        other = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.QUEEN, Suit.HEARTS),
            Card(Rank.QUEEN, Suit.CLUBS),
        ]
        result = _rollout_discard(current, other, rollout_ai, defensive=True)
        assert result in current  # no crash, returns a legal discard


class TestJointTurnEvaluation:
    def _knockable_hand(self) -> Hand:
        """11-card hand: discarding KD leaves 3 melds + 2H = 2 deadwood."""
        return Hand([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.SEVEN, Suit.HEARTS),
            Card(Rank.EIGHT, Suit.HEARTS),
            Card(Rank.NINE, Suit.HEARTS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.KING, Suit.DIAMONDS),
        ])

    def test_plan_created_and_consumed(self):
        random.seed(99)
        ai = MonteCarloAI(make_test_config())
        hand = self._knockable_hand()
        ai._current_context = make_context(hand)

        discard = ai.decide_discard(hand)
        assert ai._turn_plan is not None
        assert ai._turn_plan['discard'] == discard
        assert ai._turn_plan['knock_avg'] is not None

        test_hand = Hand([c for c in hand if c != discard])
        ai.should_knock(test_hand, ai._current_context, pending_discard=discard)
        assert ai._turn_plan is None  # consumed
        assert ai.last_mc_thinking['knock']['reason'] == 'joint_plan'

    def test_plan_ignored_for_different_discard(self):
        random.seed(99)
        ai = MonteCarloAI(make_test_config())
        hand = self._knockable_hand()
        ai._current_context = make_context(hand)

        ai.decide_discard(hand)
        plan_discard = ai._turn_plan['discard']
        other_card = next(c for c in hand if c != plan_discard)

        test_hand = Hand([c for c in hand if c != other_card])
        ai.should_knock(test_hand, ai._current_context, pending_discard=other_card)
        # Plan must not have been consumed for a mismatched discard
        # (should_knock ran its own evaluation / eligibility check instead)
        assert ai._turn_plan is not None
        knock_thinking = ai.last_mc_thinking['knock']
        assert knock_thinking is None or knock_thinking.get('reason') != 'joint_plan'

    def test_no_plan_when_disabled(self):
        random.seed(99)
        ai = MonteCarloAI(make_test_config(joint_turn_evaluation=False))
        hand = self._knockable_hand()
        ai._current_context = make_context(hand)

        ai.decide_discard(hand)
        assert ai._turn_plan is None

    def test_hypothetical_discard_does_not_set_plan(self):
        random.seed(99)
        ai = MonteCarloAI(make_test_config())
        hand = self._knockable_hand()
        ai._current_context = make_context(hand)

        ai._in_hypothetical = True
        try:
            ai.decide_discard(hand)
        finally:
            ai._in_hypothetical = False
        assert ai._turn_plan is None
