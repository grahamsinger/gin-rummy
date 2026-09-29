"""Regression tests for bugs found in the 2026-07-12 code review.

IDs (E1, E2, ...) are the review's numbering; the fixed-bug list that explained them
was removed from TODO.md on 2026-09-29 and is in its git history.
"""

import pytest

from gin_rummy.ai.opponent_model import OpponentModel
from gin_rummy.game import Game, GamePhase, InvalidActionError
from gin_rummy.models.card import Card, Rank, Suit
from gin_rummy.models.game_context import KnownCards
from gin_rummy.models.hand import Hand
from gin_rummy.models.melds import (
    Meld,
    MeldType,
    calculate_layoff,
    find_layoff_cards,
)


def _start_round(game: Game) -> None:
    """Deal and play the opening discard so the dealer is in DRAWING phase."""
    game.deal()
    game.discard_to_start(game.current_player.hand[0])


class TestE1DiscardBackRule:
    """E1: cannot discard the card just taken from the discard pile."""

    def test_discard_back_raises(self):
        game = Game("Alice", "Bob")
        _start_round(game)

        card = game.draw_from_discard()
        with pytest.raises(InvalidActionError):
            game.discard(card)

    def test_discard_other_card_allowed(self):
        game = Game("Alice", "Bob")
        _start_round(game)

        drawn = game.draw_from_discard()
        other = next(c for c in game.current_player.hand if c != drawn)
        game.discard(other)  # should not raise
        assert game.top_of_discard == other

    def test_deck_draw_can_be_discarded(self):
        game = Game("Alice", "Bob")
        _start_round(game)

        card = game.draw_from_deck()
        game.discard(card)  # legal: card came from the deck
        assert game.top_of_discard == card

    def test_knock_with_discard_blocks_drawn_discard(self):
        game = Game("Alice", "Bob")
        _start_round(game)

        card = game.draw_from_discard()
        with pytest.raises(InvalidActionError):
            game.knock_with_discard(card)

    def test_blocked_card_resets_next_turn(self):
        game = Game("Alice", "Bob")
        _start_round(game)

        drawn = game.draw_from_discard()
        assert game.discard_blocked_card == drawn
        other = next(c for c in game.current_player.hand if c != drawn)
        game.discard(other)
        assert game.discard_blocked_card is None


class TestE2OptimalLayoff:
    """E2: layoff must not depend on meld order; it should maximize value."""

    def _melds(self):
        set5 = Meld(
            (
                Card(Rank.FIVE, Suit.HEARTS),
                Card(Rank.FIVE, Suit.DIAMONDS),
                Card(Rank.FIVE, Suit.CLUBS),
            ),
            MeldType.SET,
        )
        run678 = Meld(
            (
                Card(Rank.SIX, Suit.SPADES),
                Card(Rank.SEVEN, Suit.SPADES),
                Card(Rank.EIGHT, Suit.SPADES),
            ),
            MeldType.RUN,
        )
        return set5, run678

    def test_chain_layoff_not_blocked_by_meld_order(self):
        set5, run678 = self._melds()
        defender = [Card(Rank.FIVE, Suit.SPADES), Card(Rank.FOUR, Suit.SPADES)]

        # 5S must go on the run (not the set) so 4S can chain onto it.
        # Both meld orders must produce the same, complete layoff.
        for melds in ([set5, run678], [run678, set5]):
            laid_off = find_layoff_cards(defender, melds)
            assert set(laid_off) == set(defender), (
                f"expected both cards laid off with meld order {[str(m) for m in melds]}, got {laid_off}"
            )

    def test_layoff_maximizes_value(self):
        # 5S fits both melds; K5-chain via run is worth more in total.
        set5, run678 = self._melds()
        defender = [
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),  # not layoffable
        ]
        result = calculate_layoff(defender, [set5, run678])
        assert set(result.layoff_cards) == {
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.FOUR, Suit.SPADES),
        }
        assert result.deadwood_after == 10  # only the king remains


class TestE3RoundResultDeadwood:
    """E3: reported deadwood must match the values used for scoring."""

    def test_loser_deadwood_reflects_layoff(self):
        game = Game("Alice", "Bob")
        _start_round(game)

        knocker = game.current_player
        defender = game.opponent
        knocker.hand._cards = [
            Card(Rank.FIVE, Suit.HEARTS),
            Card(Rank.FIVE, Suit.DIAMONDS),
            Card(Rank.FIVE, Suit.CLUBS),
            Card(Rank.SIX, Suit.SPADES),
            Card(Rank.SEVEN, Suit.SPADES),
            Card(Rank.EIGHT, Suit.SPADES),
            Card(Rank.NINE, Suit.HEARTS),
            Card(Rank.TEN, Suit.HEARTS),
            Card(Rank.JACK, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
        ]
        knocker.hand._invalidate_cache()
        defender.hand._cards = [
            Card(Rank.NINE, Suit.SPADES),  # lays off on 6-7-8 run
            Card(Rank.TEN, Suit.SPADES),  # chain layoff
            Card(Rank.KING, Suit.CLUBS),
            Card(Rank.KING, Suit.DIAMONDS),
            Card(Rank.QUEEN, Suit.CLUBS),
            Card(Rank.QUEEN, Suit.DIAMONDS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
            Card(Rank.FOUR, Suit.DIAMONDS),
            Card(Rank.SIX, Suit.CLUBS),
        ]
        defender.hand._invalidate_cache()
        game.phase = GamePhase.DISCARDING

        result = game.knock()

        assert result.is_gin is False
        assert result.is_undercut is False
        # Points must equal the difference of the reported deadwood values
        assert result.points == result.loser_deadwood - result.winner_deadwood
        # Defender laid off 9S+10S (19 points): 74 raw -> 55 post-layoff
        assert result.defender_deadwood_before_layoff == 74
        assert result.loser_deadwood == 55


class TestE4KnockHandSize:
    """E4: cannot knock while holding 11 cards (must discard first)."""

    def test_knock_with_11_cards_raises(self):
        game = Game("Alice", "Bob")
        _start_round(game)
        game.draw_from_deck()  # 11 cards, DISCARDING phase

        # Force deadwood under threshold so only the size check can reject
        game.current_player.hand._cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.FIVE, Suit.HEARTS),
            Card(Rank.SIX, Suit.HEARTS),
            Card(Rank.SEVEN, Suit.HEARTS),
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.TWO, Suit.DIAMONDS),
        ]
        game.current_player.hand._invalidate_cache()

        with pytest.raises(InvalidActionError, match="10 cards"):
            game.knock()

    def test_knock_with_discard_succeeds(self):
        game = Game("Alice", "Bob")
        _start_round(game)
        game.draw_from_deck()

        game.current_player.hand._cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.FIVE, Suit.HEARTS),
            Card(Rank.SIX, Suit.HEARTS),
            Card(Rank.SEVEN, Suit.HEARTS),
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.KING, Suit.DIAMONDS),
        ]
        game.current_player.hand._invalidate_cache()

        result = game.knock_with_discard(Card(Rank.KING, Suit.DIAMONDS))
        assert result.knocker is not None
        assert game.top_of_discard == Card(Rank.KING, Suit.DIAMONDS)
        assert game.discard_history[-1] == Card(Rank.KING, Suit.DIAMONDS)


class TestA2StatisticalPhantomDiscards:
    """A2: hypothetical discard evaluations must not pollute learned stats."""

    def test_draw_evaluation_records_no_discards(self):
        from gin_rummy.ai.statistical import StatisticalAI

        ai = StatisticalAI()
        ai._round_discards.clear()

        hand = Hand(
            [
                Card(Rank.TWO, Suit.HEARTS),
                Card(Rank.FIVE, Suit.CLUBS),
                Card(Rank.SEVEN, Suit.DIAMONDS),
                Card(Rank.NINE, Suit.SPADES),
                Card(Rank.JACK, Suit.HEARTS),
                Card(Rank.KING, Suit.CLUBS),
                Card(Rank.ACE, Suit.DIAMONDS),
                Card(Rank.FOUR, Suit.SPADES),
                Card(Rank.SIX, Suit.HEARTS),
                Card(Rank.EIGHT, Suit.CLUBS),
            ]
        )
        # Draw decision internally simulates a discard via _card_helps_hand;
        # that hypothetical must not be recorded as a real discard
        ai.decide_draw(hand, Card(Rank.TEN, Suit.DIAMONDS))
        assert ai._round_discards == []

        # A real discard IS recorded
        hand.add(Card(Rank.TEN, Suit.DIAMONDS))
        ai.decide_discard(hand)
        assert len(ai._round_discards) == 1


class TestA4OpponentHeldOutsAreDead:
    """A4: cards known to be in the opponent's hand are not live outs."""

    def test_unavailable_cards_includes_opponent_hand(self):
        seven_s = Card(Rank.SEVEN, Suit.SPADES)
        buried = Card(Rank.KING, Suit.CLUBS)
        kc = KnownCards(
            my_hand=frozenset(),
            opponent_hand_known=frozenset({seven_s}),
            discard_top=None,
            discard_buried=frozenset({buried}),
        )
        assert seven_s in kc.unavailable_cards
        assert buried in kc.unavailable_cards
        # dead_cards keeps its original (buried-only) meaning for the UI
        assert seven_s not in kc.dead_cards


class TestA8OpponentModelRediscard:
    """A8: a picked-up card thrown back must be un-tracked."""

    def test_rediscard_clears_inference(self):
        model = OpponentModel()
        eight_d = Card(Rank.EIGHT, Suit.DIAMONDS)
        eight_h = Card(Rank.EIGHT, Suit.HEARTS)

        model.record_pickup(eight_d)
        model.record_pickup(eight_h)
        assert model.is_rank_dangerous(Rank.EIGHT)
        assert len(model.inferred_melds) > 0  # inferred 8s set

        # Opponent throws both back - they're clearly not collecting 8s
        model.record_discard(eight_d)
        model.record_discard(eight_h)
        assert not model.is_rank_dangerous(Rank.EIGHT)
        assert model.total_pickups == 0
        assert all(eight_d not in m.cards and eight_h not in m.cards for m in model.inferred_melds)


class TestBuriedDiscardsExcludeOwnPickups:
    """Cards a player picked up from the discard pile are in their hand,
    not buried - get_game_context must not report them as dead."""

    def test_own_pickup_not_buried(self):
        game = Game("Alice", "Bob")
        _start_round(game)

        # Dealer takes the opening discard, throws something else
        picked = game.draw_from_discard()
        other = next(c for c in game.current_player.hand if c != picked)
        game.discard(other)

        # Next turn: picker's context must not list the held card as buried
        picker_idx = 1 - game.current_player_idx
        ctx = game.get_game_context(picker_idx)
        assert picked in game.players[picker_idx].hand
        assert picked not in ctx.dead_cards
        assert picked not in ctx.known_cards.discard_buried


class TestKnockThresholdPropagation:
    """A7: GameContext carries the live (possibly Oklahoma) knock threshold."""

    def test_context_has_oklahoma_threshold(self):
        game = Game("Alice", "Bob", is_oklahoma_gin=True)
        game.deal()
        game.upcard = Card(Rank.THREE, Suit.HEARTS)

        ctx = game.get_game_context(0)
        assert ctx.knock_threshold == 3

    def test_context_has_standard_threshold(self):
        game = Game("Alice", "Bob")
        game.deal()

        ctx = game.get_game_context(0)
        assert ctx.knock_threshold == 10
