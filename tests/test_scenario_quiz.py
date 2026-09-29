"""Scenario-quiz generation: seeded positions must not change under refactors.

The golden file holds the positions (and the panel's draw advice) for a few
consecutive seeds. Regenerate with UPDATE_GOLDEN=1 after an intentional change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from gin_rummy.ai import BasicAI, ContextAwareAI
from gin_rummy.config import Config
from gin_rummy.game import GamePhase
from gin_rummy.scenario.core import (
    HUMAN_SEAT,
    PanelMember,
    describe_position,
    generate_stable_scenario,
)

GOLDEN = Path(__file__).parent / "golden" / "scenarios_seed7.json"


def _panel() -> list[PanelMember]:
    cfg = Config()
    return [PanelMember("BasicAI", BasicAI(cfg)), PanelMember("ContextAwareAI", ContextAwareAI(cfg))]


class TestScenarioGeneration:
    def test_generated_position_is_at_the_human_draw(self):
        panel = _panel()
        game = generate_stable_scenario(7, panel)
        assert game is not None
        assert game.phase == GamePhase.DRAWING and game.current_player_idx == HUMAN_SEAT
        assert len(game.players[HUMAN_SEAT].hand) == 10
        assert game.top_of_discard is not None

    def test_seeded_positions_match_golden(self):
        panel = _panel()
        actual = []
        for seed in range(7, 12):
            game = generate_stable_scenario(seed, panel)
            actual.append(None if game is None else describe_position(game, panel))

        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.write_text(json.dumps(actual, indent=1) + "\n")
        expected = json.loads(GOLDEN.read_text())
        assert actual == expected, f"positions differ from {GOLDEN.name} (UPDATE_GOLDEN=1 to accept)"
