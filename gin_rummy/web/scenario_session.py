"""Web session wrapper for the scenario quiz."""

from __future__ import annotations

import random
import threading
from concurrent.futures import Executor
from typing import Any

from gin_rummy.ai import DrawChoice
from gin_rummy.game import Game
from gin_rummy.game_runner import calculate_post_discard_deadwood
from gin_rummy.models import Card, Hand
from gin_rummy.scenario_quiz import (
    HUMAN_SEAT,
    PanelMember,
    build_panel,
    generate_stable_scenario,
    panel_discard_choices,
    panel_draw_choices,
    panel_knock_choices,
)
from gin_rummy.web.game_session import card_to_dict

# Web defaults: ~2-4s per reveal (see experiments/mc_timing.py)
WEB_MC_SIMS = 500
WEB_MC_WORKERS = 8


class ScenarioSession:
    """One user's scenario-quiz state (parallel to GameSession)."""

    def __init__(
        self, mc_sims: int = WEB_MC_SIMS, mc_workers: int = WEB_MC_WORKERS, pool: Executor | None = None
    ) -> None:
        self.mc_sims = mc_sims
        self.mc_workers = mc_workers
        self.pool = pool  # borrowed executor for the MC panel member
        self.owner_lock = threading.Lock()  # replaced by the owning GameSession's lock in the app
        self.panel: list[PanelMember] | None = None
        self.game: Game | None = None
        self.phase: str = "idle"  # idle | draw | discard | knock | done
        self.seed: int | None = None
        self.scenario_num: int = 0
        self.drawn_card: Card | None = None
        self.user_discard: Card | None = None
        self.post_discard_deadwood: int | None = None
        self.reveals: dict[str, Any] = {}
        self.tallies: dict[str, dict[str, int]] = {}
        self.decisions: dict[str, int] = {"draw": 0, "discard": 0, "knock": 0}

    def _ensure_panel(self) -> list[PanelMember]:
        if self.panel is None:
            self.panel = build_panel(self.mc_sims, self.mc_workers, pool=self.pool)
            self.tallies = {m.name: {"draw": 0, "discard": 0, "knock": 0} for m in self.panel}
        return self.panel

    def shutdown(self) -> None:
        for member in self.panel or []:
            member.ai.shutdown()  # only releases pools the AI owns

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def new_scenario(self, seed: int | None = None) -> dict[str, Any]:
        panel = self._ensure_panel()

        base = seed if seed is not None else random.randrange(1_000_000)
        game = generate_stable_scenario(base, panel)
        if game is None:
            return {"error": "Could not generate a stable scenario, try again"}

        self.game = game
        self.seed = base
        self.scenario_num += 1
        self.phase = "draw"
        self.drawn_card = None
        self.user_discard = None
        self.post_discard_deadwood = None
        self.reveals = {}
        return self.get_state()

    def answer_draw(self, source: str) -> dict[str, Any]:
        if self.game is None or self.phase != "draw":
            return {"error": "Not expecting a draw decision"}

        user_choice = DrawChoice.DISCARD if source == "discard" else DrawChoice.DECK

        # Panel evaluates the position BEFORE the draw happens
        choices = panel_draw_choices(self._ensure_panel(), self.game)
        self.decisions["draw"] += 1
        reveal = []
        for entry in choices:
            agrees = entry["choice"] == user_choice
            self.tallies[entry["name"]]["draw"] += agrees
            reveal.append(
                {
                    "name": entry["name"],
                    "choice": "discard" if entry["choice"] == DrawChoice.DISCARD else "deck",
                    "reasoning": entry["reasoning"],
                    "agrees": agrees,
                }
            )
        self.reveals["draw"] = reveal

        if user_choice == DrawChoice.DISCARD:
            self.drawn_card = self.game.draw_from_discard()
        else:
            self.drawn_card = self.game.draw_from_deck()
        self.phase = "discard"
        return self.get_state()

    def answer_discard(self, card_id: str) -> dict[str, Any]:
        if self.game is None or self.phase != "discard":
            return {"error": "Not expecting a discard decision"}

        try:
            card = Card.parse(card_id)
        except (KeyError, IndexError, ValueError):
            return {"error": f"Unknown card: {card_id}"}

        human = self.game.players[HUMAN_SEAT]
        if card not in human.hand:
            return {"error": f"{card} is not in your hand"}
        if card == self.game.discard_blocked_card:
            return {"error": f"Cannot discard {card} - you just took it from the pile"}

        choices = panel_discard_choices(self._ensure_panel(), self.game)
        self.decisions["discard"] += 1
        reveal = []
        for entry in choices:
            agrees = entry["card"] == card
            self.tallies[entry["name"]]["discard"] += agrees
            mc_evs = None
            if entry["mc_candidates"]:
                mc_evs = [{"card": c["card"], "ev": c["avg_points"]} for c in entry["mc_candidates"][:5]]
            reveal.append(
                {
                    "name": entry["name"],
                    "choice": str(entry["card"]),
                    "choice_id": entry["card"].code,
                    "reasoning": entry["reasoning"],
                    "agrees": agrees,
                    "mc_evs": mc_evs,
                }
            )
        self.reveals["discard"] = reveal

        self.user_discard = card
        self.post_discard_deadwood = calculate_post_discard_deadwood(human.hand, card)
        if self.post_discard_deadwood <= self.game.knock_threshold:
            self.phase = "knock"
        else:
            self.phase = "done"
        return self.get_state()

    def answer_knock(self, knock: bool) -> dict[str, Any]:
        if self.game is None or self.phase != "knock" or self.user_discard is None:
            return {"error": "Not expecting a knock decision"}

        human = self.game.players[HUMAN_SEAT]
        post_hand = Hand([c for c in human.hand if c != self.user_discard])
        choices = panel_knock_choices(self._ensure_panel(), self.game, post_hand, self.user_discard)
        self.decisions["knock"] += 1
        reveal = []
        for entry in choices:
            agrees = entry["knocks"] == knock
            self.tallies[entry["name"]]["knock"] += agrees
            reveal.append(
                {
                    "name": entry["name"],
                    "choice": "knock" if entry["knocks"] else "continue",
                    "reasoning": entry["reasoning"],
                    "agrees": agrees,
                }
            )
        self.reveals["knock"] = reveal
        self.phase = "done"
        return self.get_state()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        if self.game is None:
            return {
                "phase": "idle",
                "scenario_num": self.scenario_num,
                "tallies": self.tallies,
                "decisions": self.decisions,
            }

        human = self.game.players[HUMAN_SEAT]
        analysis = human.hand.analyze()
        ctx = self.game.get_game_context(HUMAN_SEAT)

        melds = [
            {
                "type": "set" if meld.meld_type.name == "SET" else "run",
                "cards": [c.code for c in meld.cards],
            }
            for meld in analysis.melds
        ]

        return {
            "phase": self.phase,
            "scenario_num": self.scenario_num,
            "seed": self.seed,
            "hand": [card_to_dict(c) for c in human.hand],
            "melds": melds,
            "deadwood": analysis.deadwood_value,
            "deadwood_cards": [c.code for c in analysis.deadwood_cards],
            "discard_top": card_to_dict(self.game.top_of_discard) if self.game.top_of_discard else None,
            "deck_remaining": len(self.game.deck),
            "knock_threshold": self.game.knock_threshold,
            "opponent_pickups": [c.code for c in ctx.opponent_pickups],
            "buried": [c.code for c in sorted(ctx.dead_cards)],
            "drawn_card": card_to_dict(self.drawn_card) if self.drawn_card else None,
            "blocked_card": self.game.discard_blocked_card.code if self.game.discard_blocked_card else None,
            "user_discard": self.user_discard.code if self.user_discard else None,
            "post_discard_deadwood": self.post_discard_deadwood,
            "reveals": self.reveals,
            "tallies": self.tallies,
            "decisions": self.decisions,
        }
