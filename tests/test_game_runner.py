"""Tests for the shared AI turn runner."""

from __future__ import annotations

import random
from typing import ClassVar

import pytest

import gin_rummy.config as config_module
from gin_rummy.ai import BasicAI
from gin_rummy.config import Config
from gin_rummy.game import Game
from gin_rummy.game_runner import execute_ai_turn
from gin_rummy.models import Card, Rank, Suit
from gin_rummy.round_runner import AISeat


class TrackingAI(BasicAI):
    """An AI that tracks opponent actions but is not a ContextAwareAI."""

    def __init__(self) -> None:
        super().__init__()
        self.pickups: list[Card] = []
        self.discards: list[Card] = []

    def record_opponent_pickup(self, card: Card) -> None:
        self.pickups.append(card)

    def record_opponent_discard(self, card: Card) -> None:
        self.discards.append(card)


class TestOpponentTrackingForwarding:
    """B4: forwarding must be by capability, not by concrete class."""

    def test_seat_forwards_to_any_ai_with_the_methods(self):
        ai = TrackingAI()
        seat = AISeat(ai)
        card = Card(Rank.SEVEN, Suit.HEARTS)
        seat.observe_pickup(card)
        seat.observe_discard(card)
        assert ai.pickups == [card]
        assert ai.discards == [card]

    def test_plain_basic_ai_accepts_the_calls(self):
        seat = AISeat(BasicAI())
        card = Card(Rank.SEVEN, Suit.HEARTS)
        seat.observe_pickup(card)
        seat.observe_discard(card)
        assert seat.ai.opponent_model.total_discards == 1


class ContextSpyAI(BasicAI):
    """Records the context every discard decision receives."""

    needs_context: ClassVar[bool] = True

    def __init__(self) -> None:
        super().__init__()
        self.discard_contexts: list = []

    def decide_discard(self, hand, context=None):
        self.discard_contexts.append(context)
        return super().decide_discard(hand, context)

    def decide_discard_with_reasoning(self, hand, context=None):
        self.discard_contexts.append(context)
        return super().decide_discard_with_reasoning(hand, context)


class TestDiscardGetsTheContext:
    """Discard decisions used to be made without a game context (audit finding, 2026-09-29)."""

    @staticmethod
    def _dealt() -> tuple[Game, ContextSpyAI]:
        random.seed(5)
        game = Game("Spy", "Other")
        game.deal()
        return game, ContextSpyAI()

    def test_opening_discard_through_the_seat(self):
        game, ai = self._dealt()
        AISeat(ai).opening_discard(game)
        assert len(ai.discard_contexts) == 1 and ai.discard_contexts[0] is not None

    def test_opening_discard_through_the_cli(self, monkeypatch):
        cfg = Config()
        cfg.display.ai_turn_delay = 0.0
        monkeypatch.setattr(config_module, "_config", cfg)
        from gin_rummy import cli

        game, ai = self._dealt()
        cli.play_ai_first_discard(game, ai)
        assert len(ai.discard_contexts) == 1 and ai.discard_contexts[0] is not None

    def test_opening_discard_through_the_web_session(self, isolated_db):
        from gin_rummy.game import GamePhase
        from gin_rummy.web.game_session import GameSession

        session = GameSession()
        for seed in range(50):  # find a deal where the AI is the non-dealer
            random.seed(seed)
            session.new_game(player_name="T", ai_difficulty="easy")
            game = session.game
            assert game is not None
            if game.phase == GamePhase.FIRST_DISCARD and game.current_player_idx != session.human_idx:
                break
        else:
            pytest.fail("no deal with the AI opening in 50 seeds")
        ai = ContextSpyAI()
        session.ai = ai
        session.ai_turn()
        assert game.phase == GamePhase.DRAWING
        assert len(ai.discard_contexts) == 1 and ai.discard_contexts[0] is not None

    def test_turn_discard_with_and_without_reasoning(self):
        for capture in (False, True):
            game, ai = self._dealt()
            game.discard_to_start(game.current_player.hand[0])
            _, actions, _ = execute_ai_turn(game, ai, capture_reasoning=capture)
            assert ai.discard_contexts and all(c is not None for c in ai.discard_contexts)
            assert actions is not None
            # the real discard decision (the last call; earlier ones are the draw
            # evaluation's hypothetical discards) sees the post-draw state
            final = ai.discard_contexts[-1]
            assert final.drawn_card == actions.drawn_card
            assert final.deck_remaining == len(game.deck)

    def test_context_carries_the_drawn_card_only_for_the_player_on_turn(self):
        game, _ = self._dealt()
        game.discard_to_start(game.current_player.hand[0])
        idx = game.current_player_idx
        assert game.get_game_context(idx).drawn_card is None
        card = game.draw_from_deck()
        assert game.get_game_context(idx).drawn_card == card
        assert game.get_game_context(1 - idx).drawn_card is None
