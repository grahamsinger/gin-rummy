"""The shared round loop (AUDIT §2.1): seats decide, the runner drives and relays."""

from __future__ import annotations

import random

import pytest

import gin_rummy.config as config_module
from gin_rummy.ai import BasicAI, DrawChoice
from gin_rummy.config import Config
from gin_rummy.game import Game, GamePhase
from gin_rummy.game_runner import TurnResult
from gin_rummy.models import Card
from gin_rummy.round_runner import AISeat, RoundOutcome, run_round


class TrackingAI(BasicAI):
    """Remembers what it was told about the opponent."""

    def __init__(self) -> None:
        super().__init__()
        self.pickups: list[Card] = []
        self.discards: list[Card] = []
        self.resets = 0

    def record_opponent_pickup(self, card: Card) -> None:
        self.pickups.append(card)

    def record_opponent_discard(self, card: Card) -> None:
        self.discards.append(card)

    def reset_for_new_hand(self) -> None:
        super().reset_for_new_hand()
        self.resets += 1


class ActionLog:
    """Turn callbacks that keep every completed turn."""

    def __init__(self) -> None:
        self.turns = []

    def on_draw(self, player, source, card) -> None:
        pass

    def on_discard(self, player, card) -> None:
        pass

    def on_knock(self, player, discard, deadwood, result) -> None:
        pass

    def on_turn_complete(self, player, actions) -> None:
        self.turns.append((player.name, actions))


def _dealt_game(seed: int = 3) -> Game:
    random.seed(seed)
    game = Game("A", "B")
    game.deal()
    return game


class TestRunRound:
    def test_needs_a_dealt_game(self):
        with pytest.raises(ValueError):
            run_round(Game("A", "B"), [AISeat(BasicAI()), AISeat(BasicAI())])

    def test_relays_every_opponent_action_to_the_other_seat(self):
        game = _dealt_game()
        ais = [TrackingAI(), TrackingAI()]
        logs = [ActionLog(), ActionLog()]
        seats = [AISeat(ais[0], callbacks=logs[0]), AISeat(ais[1], callbacks=logs[1])]

        outcome = run_round(game, seats)

        assert isinstance(outcome, RoundOutcome) and outcome.result is not None
        assert outcome.ended_by in (TurnResult.KNOCKED, TurnResult.DRAW)
        assert outcome.turns == len(logs[0].turns) + len(logs[1].turns)
        assert [ai.resets for ai in ais] == [1, 1]

        opener = 1 - game.dealer_idx
        for idx in range(2):
            other = 1 - idx
            mine = [actions for _, actions in logs[idx].turns]
            expected_pickups = [a.drawn_card for a in mine if a.draw_source == DrawChoice.DISCARD]
            expected_discards = [a.discarded_card for a in mine if not a.did_knock]
            if idx == opener:
                expected_discards.insert(0, game.discard_history[0])
            assert ais[other].pickups == expected_pickups
            assert ais[other].discards == expected_discards

    def test_stop_when_freezes_the_round(self):
        game = _dealt_game()
        outcome = run_round(game, [AISeat(BasicAI()), AISeat(BasicAI())], stop_when=lambda g, turns: turns == 3)
        assert outcome == RoundOutcome(result=None, ended_by=TurnResult.CONTINUE, turns=3)
        assert game.phase == GamePhase.DRAWING

    def test_deck_exhaustion_is_a_draw(self):
        game = _dealt_game()
        game.deck._cards = game.deck._cards[: game.min_deck_cards]
        outcome = run_round(game, [AISeat(BasicAI()), AISeat(BasicAI())])
        assert outcome.ended_by == TurnResult.DRAW
        assert outcome.result is not None and outcome.result.is_draw


class TestCliSeats:
    def test_player_vs_player_round_runs_on_scripted_input(self, monkeypatch: pytest.MonkeyPatch, capsys):
        from gin_rummy import cli

        cfg = Config()
        cfg.display.clear_screen = False
        cfg.display.ai_turn_delay = 0.0
        monkeypatch.setattr(config_module, "_config", cfg)

        prompts: list[str] = []

        def scripted_input(prompt: str = "") -> str:
            prompts.append(prompt)
            if "Your choice" in prompt:
                return "1"
            if "Card # to discard" in prompt or "Card to discard" in prompt:
                return "1"
            if "Knock?" in prompt:
                return "y"
            if "Discard anyway" in prompt:
                return "y"
            return ""

        monkeypatch.setattr("builtins.input", scripted_input)

        random.seed(11)
        game = Game("P1", "P2")
        cli.play_round_pvp(game, tracker=None)

        assert game.phase in (GamePhase.KNOCKED, GamePhase.ROUND_OVER)
        hand_overs = [p for p in prompts if "next player's turn" in p]
        turns = [p for p in prompts if "Your choice" in p]
        assert len(hand_overs) == len(turns)  # one hand-over before every turn, none after the last
        out = capsys.readouterr().out
        assert "ROUND OVER" in out or "Round ended in a DRAW" in out
