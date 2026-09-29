"""Scenario positions and the AI panel, shared by the terminal quiz and the web quiz.

A scenario is a real hand played by two AIs for a random number of turns
and frozen at the human seat's draw, so the position has a genuine
discard history and opponent-tracking data. The panel is the set of AIs
whose advice is compared with the player's choices."""

from __future__ import annotations

import random
from concurrent.futures import Executor
from dataclasses import dataclass, replace

from gin_rummy.ai import BasicAI, ContextAwareAI, DrawChoice, MonteCarloAI
from gin_rummy.config import get_config
from gin_rummy.game import Game
from gin_rummy.models import Card, Hand
from gin_rummy.round_runner import AISeat, run_round

HUMAN_SEAT = 0
MAX_GENERATION_ATTEMPTS = 50


@dataclass
class PanelMember:
    """One AI whose choices are compared against the player's."""

    name: str
    ai: BasicAI
    draw_agreements: int = 0
    discard_agreements: int = 0
    knock_agreements: int = 0


class _PanelFeedCallbacks:
    """Turn callbacks that feed opponent actions to the panel AIs.

    The panel advises HUMAN_SEAT, so it observes the other player.
    """

    def __init__(self, panel: list[PanelMember], opponent_name: str) -> None:
        self.panel = panel
        self.opponent_name = opponent_name

    def _context_members(self):
        return [m.ai for m in self.panel]

    def on_draw(self, player, source, card) -> None:
        if player.name == self.opponent_name and source == DrawChoice.DISCARD:
            for ai in self._context_members():
                ai.record_opponent_pickup(card)

    def on_discard(self, player, card) -> None:
        if player.name == self.opponent_name:
            for ai in self._context_members():
                ai.record_opponent_discard(card)

    def on_knock(self, player, discard, deadwood, result) -> None:
        pass

    def on_turn_complete(self, player, actions) -> None:
        pass


def build_panel(mc_sims: int, mc_workers: int, pool: Executor | None = None) -> list[PanelMember]:
    """Create the advisor AIs. `pool` lends MonteCarloAI an executor instead of starting its own."""
    cfg = get_config()
    mc_cfg = replace(
        cfg.monte_carlo_ai,
        draw_simulations=mc_sims,
        discard_simulations=mc_sims,
        knock_simulations=mc_sims,
        max_workers=mc_workers,
    )
    mc_config = replace(cfg, monte_carlo_ai=mc_cfg)
    return [
        PanelMember("BasicAI", BasicAI()),
        PanelMember("ContextAwareAI", ContextAwareAI()),
        PanelMember("MonteCarloAI", MonteCarloAI(mc_config, pool=pool)),
    ]


def generate_scenario(
    seed: int,
    panel: list[PanelMember],
    min_turns: int = 4,
    max_turns: int = 14,
) -> Game | None:
    """Play a real hand between two AIs and freeze it at the human seat.

    Returns a Game in DRAWING phase with current player == HUMAN_SEAT,
    or None if this seed's hand ended before reaching the target turn.
    """
    random.seed(seed)
    target_turns = random.randint(min_turns, max_turns)
    max_total_turns = max_turns * 3

    game = Game("You", "Opponent")
    game.deal()

    # AIs that actually play out the position (independent of the panel).
    # Only the opponent's actions are fed to the panel.
    callbacks = _PanelFeedCallbacks(panel, opponent_name="Opponent")
    seats = [AISeat(ContextAwareAI(), callbacks=None if i == HUMAN_SEAT else callbacks) for i in range(2)]

    def frozen(game: Game, turns: int) -> bool:
        return (turns >= target_turns and game.current_player_idx == HUMAN_SEAT) or turns > max_total_turns

    outcome = run_round(game, seats, stop_when=frozen)
    if outcome.result is not None or outcome.turns > max_total_turns:
        return None  # knock or deck exhaustion, or the hand ran too long: unusable
    return game


def reset_panel_tracking(panel: list[PanelMember]) -> None:
    """Clear per-hand opponent tracking on every panel member."""
    for member in panel:
        member.ai.reset_for_new_hand()


def generate_stable_scenario(base_seed: int, panel: list[PanelMember]) -> Game | None:
    """Retry generate_scenario with derived seeds until one reaches the human seat.

    Each attempt plays a fresh hand, so the panel forgets what it saw during
    a failed attempt (the callbacks feed it opponent actions).
    """
    for attempt in range(MAX_GENERATION_ATTEMPTS):
        reset_panel_tracking(panel)
        game = generate_scenario(base_seed + attempt * 1000, panel)
        if game is not None:
            return game
    return None


def describe_position(game: Game, panel: list[PanelMember]) -> dict:
    """The frozen position, and the panel's draw advice, as plain data.

    Used by the behaviour fingerprint and the golden scenario test: any
    change in generation, opponent tracking or the panel feed shows up here.
    """
    ctx = game.get_game_context(HUMAN_SEAT)
    human = game.players[HUMAN_SEAT]
    opponent = game.players[1 - HUMAN_SEAT]
    return {
        "dealer": game.dealer_idx,
        "hand": [c.code for c in human.hand],
        "opponent_hand": [c.code for c in opponent.hand],
        "discard_pile": [c.code for c in game.discard_pile],
        "deck": [c.code for c in game.deck],
        "opponent_pickups": [c.code for c in ctx.opponent_pickups],
        "dead_cards": sorted(c.code for c in ctx.dead_cards),
        "panel_draw": {e["name"]: e["choice"].name for e in panel_draw_choices(panel, game)},
    }


def panel_draw_choices(panel: list[PanelMember], game: Game) -> list[dict]:
    """Ask each panel AI for its draw choice on the current position.

    Returns one dict per AI: {name, choice (DrawChoice), reasoning}.
    """
    hand = game.players[HUMAN_SEAT].hand
    ctx = game.get_game_context(HUMAN_SEAT)
    choices = []
    for member in panel:
        reasoning = member.ai.decide_draw_with_reasoning(hand, game.top_of_discard, ctx)
        choices.append(
            {
                "name": member.name,
                "choice": reasoning.choice,
                "reasoning": reasoning.reasoning,
            }
        )
    return choices


def panel_discard_choices(panel: list[PanelMember], game: Game) -> list[dict]:
    """Ask each panel AI for its discard on the current 11-card hand.

    Returns one dict per AI: {name, card (Card), reasoning, mc_candidates}.
    mc_candidates is MC's DiscardCandidate list, best first (or None for other AIs).
    """
    hand = game.players[HUMAN_SEAT].hand
    ctx = game.get_game_context(HUMAN_SEAT)
    choices = []
    for member in panel:
        reasoning = member.ai.decide_discard_with_reasoning(hand, ctx)
        mc_candidates = None
        if isinstance(member.ai, MonteCarloAI) and member.ai.last_mc_thinking:
            thinking = member.ai.last_mc_thinking.discard
            if thinking:
                mc_candidates = thinking.candidates
        choices.append(
            {
                "name": member.name,
                "card": reasoning.card,
                "reasoning": reasoning.reasoning,
                "mc_candidates": mc_candidates,
            }
        )
    return choices


def panel_knock_choices(panel: list[PanelMember], game: Game, post_hand: Hand, pending: Card) -> list[dict]:
    """Ask each panel AI whether it would knock with the post-discard hand.

    Returns one dict per AI: {name, knocks (bool), reasoning}.
    """
    ctx = game.get_game_context(HUMAN_SEAT)
    choices = []
    for member in panel:
        reasoning = member.ai.should_knock_with_reasoning(post_hand, ctx, pending_discard=pending)
        choices.append(
            {
                "name": member.name,
                "knocks": reasoning.should_knock,
                "reasoning": reasoning.reasoning,
            }
        )
    return choices
