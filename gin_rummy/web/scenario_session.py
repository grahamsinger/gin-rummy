"""Web session wrapper for the scenario quiz."""

from __future__ import annotations

import copy
import logging
import random
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor, wait
from typing import Any

from gin_rummy.ai import DrawChoice
from gin_rummy.analysis.deep import Position, analyse, position_from_game
from gin_rummy.db.deep_analyses import find_deep_analysis, save_deep_analysis
from gin_rummy.db.scenario_stats import get_scenario_totals, record_scenario_answers
from gin_rummy.game import Game
from gin_rummy.game_runner import calculate_post_discard_deadwood
from gin_rummy.models import Card, Hand
from gin_rummy.scenario.core import (
    HUMAN_SEAT,
    PanelMember,
    build_panel,
    generate_stable_scenario,
    panel_discard_choices,
    panel_draw_choices,
    panel_knock_choices,
    split_opponent_pickups,
)
from gin_rummy.web.serializers import card_to_dict

logger = logging.getLogger(__name__)

# Web defaults: ~2-4s per reveal (see experiments/mc_timing.py)
WEB_MC_SIMS = 500
WEB_MC_WORKERS = 8

# Deep analysis on request: the most deals to try, and how many per round
DEEP_SAMPLES = 40000
DEEP_BATCH = 4000

# Cards in the deck once both hands and the first face-up card are dealt
DECK_AFTER_DEAL = 31


class ScenarioSession:
    """One user's scenario-quiz state (parallel to GameSession).

    The panel analyses a decision as soon as its position is known, which
    is before the player answers: what the AIs would do does not depend on
    what the player does. The answer is then judged against that analysis.
    Results are kept back until the scenario is complete, so an AI's
    reasoning about the draw cannot give away the discard.

    With `background=True` the analysis runs on a worker thread, so neither
    a new scenario nor an answer waits for the AIs.

    A deep analysis of a decision (gin_rummy.analysis.deep) is run on
    request once the scenario is complete. It takes minutes, runs on its
    own thread and is saved to the database, so it is there the next time
    the same position comes up.
    """

    def __init__(
        self,
        mc_sims: int = WEB_MC_SIMS,
        mc_workers: int = WEB_MC_WORKERS,
        pool: Executor | None = None,
        background: bool = False,
    ) -> None:
        self.mc_sims = mc_sims
        self.mc_workers = mc_workers
        self.pool = pool  # borrowed executor for the MC panel member
        self.background = background
        # One worker: the panel AIs are stateful, so jobs run one at a time, in the order submitted
        self._analysis_thread: ThreadPoolExecutor | None = None
        self._analyses: list[Future] = []
        self._preparing: dict[str, Future] = {}  # analysis jobs by decision, so unneeded ones can be cancelled
        self._results_lock = threading.Lock()  # guards prepared, reveals, pending, tallies and decisions
        self._prepared: dict[str, list[dict[str, Any]]] = {}  # the panel's choices, before judging
        self.pending: list[str] = []  # decisions answered but not yet judged
        self.owner_lock = threading.Lock()  # replaced by the owning GameSession's lock in the app
        self.panel: list[PanelMember] | None = None
        self.game: Game | None = None
        self.phase: str = "idle"  # idle | draw | discard | knock | done
        self.seed: int | None = None
        self.turns_at_start: int = 0  # turns both players had taken when the scenario was frozen
        self.scenario_num: int = 0
        self.drawn_card: Card | None = None
        self.user_discard: Card | None = None
        self.post_discard_deadwood: int | None = None
        self.reveals: dict[str, Any] = {}
        self.tallies: dict[str, dict[str, int]] = {}
        self.decisions: dict[str, int] = {"draw": 0, "discard": 0, "knock": 0}
        self.deep_samples = DEEP_SAMPLES
        self.deep_batch = DEEP_BATCH
        self._deep_thread: ThreadPoolExecutor | None = None
        self._deep_stop = threading.Event()
        self._deep_lock = threading.Lock()  # guards _deep_jobs
        self._deep_jobs: dict[str, dict[str, Any]] = {}  # by position key: status, progress, result
        self._positions: dict[str, Position] = {}  # this scenario's decisions as the player met them
        self._choices: dict[str, str] = {}  # the player's answers, as deep-analysis options

    def _ensure_panel(self) -> list[PanelMember]:
        if self.panel is None:
            self.panel = build_panel(self.mc_sims, self.mc_workers, pool=self.pool)
            self.tallies = {m.name: {"draw": 0, "discard": 0, "knock": 0} for m in self.panel}
        return self.panel

    def _record(self, seed: int | None, decision: str, user_choice: str, reveal: list[dict[str, Any]]) -> None:
        """Save an answered decision for the all-time scoreboard. The quiz carries on if the database is unavailable."""
        rows = [(r["name"], r.get("choice_id", r["choice"]), r["agrees"]) for r in reveal]
        try:
            record_scenario_answers(seed, decision, user_choice, rows)
        except sqlite3.Error:
            logger.warning("Could not save scenario answer", exc_info=True)

    def _run(self, job: Callable[[], None]) -> Future | None:
        """Run a job now, or queue it on the worker thread."""
        if not self.background:
            job()
            return None
        if self._analysis_thread is None:
            self._analysis_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenario-analysis")
        future = self._analysis_thread.submit(job)
        self._analyses.append(future)
        return future

    def _prepare(self, decision: str, evaluate: Callable[[], list[dict[str, Any]]]) -> None:
        """Start the panel's analysis of a decision whose position is now known.

        `evaluate` returns one row per AI; each row's "value" is what the AI
        chose, in the form the player's answer will be compared with.
        """

        def job() -> None:
            rows: list[dict[str, Any]] = []
            try:
                rows = evaluate()
            except Exception:
                logger.exception("Scenario analysis failed for the %s decision", decision)
            with self._results_lock:
                self._prepared[decision] = rows

        future = self._run(job)
        if future is not None:
            self._preparing[decision] = future

    def _judge(self, decision: str, user_choice: str, user_value: Any) -> None:
        """Compare the player's answer with the prepared analysis and store the result."""
        seed = self.seed
        self._preparing.pop(decision, None)  # answered, so its analysis is needed
        with self._results_lock:
            self.pending.append(decision)

        def job() -> None:
            with self._results_lock:
                rows = self._prepared.get(decision, [])
                reveal = [
                    {**{k: v for k, v in row.items() if k != "value"}, "agrees": row["value"] == user_value}
                    for row in rows
                ]
                if reveal:
                    self.decisions[decision] += 1
                    for row in reveal:
                        self.tallies[row["name"]][decision] += row["agrees"]
                self.reveals[decision] = reveal
                self.pending.remove(decision)
            if reveal:
                self._record(seed, decision, user_choice, reveal)

        self._run(job)

    def wait_for_analysis(self) -> None:
        """Block until every submitted job has finished."""
        wait(self._analyses)
        self._analyses.clear()

    def _prepare_draw(self) -> None:
        assert self.game is not None
        panel = self._ensure_panel()
        position = copy.deepcopy(self.game)  # the player's draw will change the game
        self._positions["draw"] = position_from_game(position, HUMAN_SEAT, "draw", self.seed)

        def evaluate() -> list[dict[str, Any]]:
            return [
                {
                    "name": entry["name"],
                    "choice": "discard" if entry["choice"] == DrawChoice.DISCARD else "deck",
                    "reasoning": entry["reasoning"],
                    "value": entry["choice"],
                }
                for entry in panel_draw_choices(panel, position)
            ]

        self._prepare("draw", evaluate)

    def _prepare_discard(self) -> None:
        assert self.game is not None
        panel = self._ensure_panel()
        position = copy.deepcopy(self.game)
        self._positions["discard"] = position_from_game(position, HUMAN_SEAT, "discard", self.seed)

        def evaluate() -> list[dict[str, Any]]:
            rows = []
            for entry in panel_discard_choices(panel, position):
                mc_evs = None
                if entry["mc_candidates"]:
                    mc_evs = [{"card": c.card, "ev": c.avg_points} for c in entry["mc_candidates"][:5]]
                rows.append(
                    {
                        "name": entry["name"],
                        "choice": str(entry["card"]),
                        "choice_id": entry["card"].code,
                        "reasoning": entry["reasoning"],
                        "value": entry["card"],
                        "mc_evs": mc_evs,
                    }
                )
            return rows

        self._prepare("discard", evaluate)

    def _prepare_knock(self) -> None:
        assert self.game is not None and self.user_discard is not None
        panel = self._ensure_panel()
        position = copy.deepcopy(self.game)
        pending_discard = self.user_discard
        post_hand = Hand([c for c in position.players[HUMAN_SEAT].hand if c != pending_discard])
        self._positions["knock"] = position_from_game(
            position, HUMAN_SEAT, "knock", self.seed, pending_discard=pending_discard
        )

        def evaluate() -> list[dict[str, Any]]:
            return [
                {
                    "name": entry["name"],
                    "choice": "knock" if entry["knocks"] else "continue",
                    "reasoning": entry["reasoning"],
                    "value": entry["knocks"],
                }
                for entry in panel_knock_choices(panel, position, post_hand, pending_discard)
            ]

        self._prepare("knock", evaluate)

    def shutdown(self) -> None:
        self._deep_stop.set()
        if self._deep_thread is not None:
            self._deep_thread.shutdown(wait=True)
        if self._analysis_thread is not None:
            self._analysis_thread.shutdown(wait=True)
        for member in self.panel or []:
            member.ai.shutdown()  # only releases pools the AI owns

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def new_scenario(self, seed: int | None = None) -> dict[str, Any]:
        panel = self._ensure_panel()
        # Analysis of a decision the player never answered is not needed: drop it if it has not started
        for future in self._preparing.values():
            future.cancel()
        self._preparing.clear()
        # The panel is about to be reused, and its answers belong to the old position
        self.wait_for_analysis()

        base = seed if seed is not None else random.randrange(1_000_000)
        game = generate_stable_scenario(base, panel)
        if game is None:
            return {"error": "Could not generate a stable scenario, try again"}

        self.game = game
        self.seed = base
        self.turns_at_start = len(game.discard_history) - (1 if game.upcard is not None else 0)
        self.scenario_num += 1
        self.phase = "draw"
        self.drawn_card = None
        self.user_discard = None
        self.post_discard_deadwood = None
        self._positions = {}
        self._choices = {}
        with self._results_lock:
            self.reveals = {}
            self._prepared = {}
        self._prepare_draw()
        return self.get_state()

    def answer_draw(self, source: str) -> dict[str, Any]:
        if self.game is None or self.phase != "draw":
            return {"error": "Not expecting a draw decision"}

        user_choice = DrawChoice.DISCARD if source == "discard" else DrawChoice.DECK

        self._judge("draw", source, user_choice)
        self._choices["draw"] = "pile" if user_choice == DrawChoice.DISCARD else "deck"

        if user_choice == DrawChoice.DISCARD:
            self.drawn_card = self.game.draw_from_discard()
        else:
            self.drawn_card = self.game.draw_from_deck()
        self.phase = "discard"
        self._prepare_discard()
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

        self._judge("discard", card.code, card)
        self._choices["discard"] = card.code

        self.user_discard = card
        self.post_discard_deadwood = calculate_post_discard_deadwood(human.hand, card)
        if self.post_discard_deadwood <= self.game.knock_threshold:
            self.phase = "knock"
            self._prepare_knock()
        else:
            self.phase = "done"
        return self.get_state()

    def answer_knock(self, knock: bool) -> dict[str, Any]:
        if self.game is None or self.phase != "knock" or self.user_discard is None:
            return {"error": "Not expecting a knock decision"}

        self._judge("knock", "knock" if knock else "continue", knock)
        self._choices["knock"] = "knock" if knock else "continue"
        self.phase = "done"
        return self.get_state()

    def start_deep_analysis(self, decision: str) -> dict[str, Any]:
        """Queue a deep analysis of one of this scenario's answered decisions."""
        position = self._positions.get(decision)
        if self.phase != "done" or position is None or decision not in self._choices:
            return {"error": f"No answered {decision} decision to analyse"}

        key = position.key
        with self._deep_lock:
            job = self._deep_jobs.get(key)
            if job is not None and job["status"] in ("queued", "running"):
                return self.get_state()
            self._deep_jobs[key] = {"status": "queued", "progress": "Waiting to start", "result": None}

        def update(**changes: Any) -> None:
            with self._deep_lock:
                self._deep_jobs[key].update(changes)

        def job_body() -> None:
            update(status="running", progress="Dealing the hidden cards")
            try:
                result = analyse(
                    position,
                    max_samples=self.deep_samples,
                    batch=self.deep_batch,
                    workers=self.mc_workers,
                    pool=self.pool,
                    progress=lambda message: update(progress=message),
                    should_stop=self._deep_stop.is_set,
                )
            except Exception:
                logger.exception("Deep analysis failed for the %s decision", decision)
                update(status="failed", progress="The analysis failed")
                return
            if self._deep_stop.is_set():
                update(status="failed", progress="Stopped")
                return
            try:
                save_deep_analysis(result)
            except sqlite3.Error:
                logger.warning("Could not save the deep analysis", exc_info=True)
            update(status="done", progress="", result=result)

        if self._deep_thread is None:
            self._deep_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenario-deep")
        future = self._deep_thread.submit(job_body)
        if not self.background:
            future.result()
        return self.get_state()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _lifetime(self) -> dict[str, Any] | None:
        try:
            return get_scenario_totals()
        except sqlite3.Error:
            logger.warning("Could not read scenario totals", exc_info=True)
            return None

    def _deep(self) -> dict[str, Any]:
        """Deep analyses of this scenario's answered decisions: running, finished now, or saved earlier."""
        if self.phase != "done":
            return {}
        deep = {}
        for decision, choice in self._choices.items():
            position = self._positions.get(decision)
            if position is None:
                continue
            with self._deep_lock:
                job = dict(self._deep_jobs.get(position.key) or {})
            if not job or job["status"] == "failed":
                try:
                    saved = find_deep_analysis(position.key)
                except sqlite3.Error:
                    saved = None
                if saved is not None:
                    job = {"status": "done", "progress": "", "result": saved}
            if not job:
                job = {"status": "none", "progress": "", "result": None}
            deep[decision] = {**job, "your_choice": choice}
        return deep

    def _results(self) -> dict[str, Any]:
        """The analysis side of the state. Reveals are held back until the scenario is complete."""
        with self._results_lock:
            pending = list(self.pending)
            complete = self.phase == "done" and not pending
            return {
                "reveals": copy.deepcopy(self.reveals) if complete else {},
                "pending": pending,
                "tallies": copy.deepcopy(self.tallies),
                "decisions": dict(self.decisions),
            }

    def get_state(self) -> dict[str, Any]:
        if self.game is None:
            return {
                "phase": "idle",
                "scenario_num": self.scenario_num,
                **self._results(),
                "lifetime": self._lifetime(),
            }

        human = self.game.players[HUMAN_SEAT]
        analysis = human.hand.analyze()
        ctx = self.game.get_game_context(HUMAN_SEAT)
        held, returned = split_opponent_pickups(ctx)
        # Every turn ends with a discard, so the scenario's starting history counts the turns so far
        turns_played = self.turns_at_start

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
            "deck_start": DECK_AFTER_DEAL,
            "deck_min": self.game.min_deck_cards,
            "turns_played": turns_played,
            "your_turn": turns_played // 2 + 1,
            "knock_threshold": self.game.knock_threshold,
            "opponent_pickups": [c.code for c in ctx.opponent_pickups],
            "opponent_holds": [c.code for c in held],
            "opponent_returned": [c.code for c in returned],
            "buried": [c.code for c in sorted(ctx.dead_cards)],
            "drawn_card": card_to_dict(self.drawn_card) if self.drawn_card else None,
            "blocked_card": self.game.discard_blocked_card.code if self.game.discard_blocked_card else None,
            "user_discard": self.user_discard.code if self.user_discard else None,
            "post_discard_deadwood": self.post_discard_deadwood,
            **self._results(),
            "deep": self._deep(),
            "lifetime": self._lifetime(),
        }
