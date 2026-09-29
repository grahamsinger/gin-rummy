"""Simulation batches, the unit of work sent to worker processes."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import TYPE_CHECKING

from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.mc.rollout import rollout, score_knock
from gin_rummy.ai.mc.sampling import _sample_state
from gin_rummy.models import Card, Hand

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


def worker_init() -> None:
    """Seed random uniquely per worker process."""
    seed = os.getpid() * 31 + int(time.time() * 1000) % 1_000_000
    random.seed(seed)


def _draw_sim_batch(
    option: str,
    my_hand: list[Card],
    discard_top: Card,
    sim_discard_base: list[Card],
    rollout_ai: BasicAI,
    max_turns: int,
    knock_threshold: int,
    gin_bonus: int,
    undercut_bonus: int,
    n_sims: int,
    samples: list[tuple[list[Card], list[Card]]] | None,
    unknown: list[Card] | None,
    opponent_known: list[Card] | None,
    min_deck_cards: int = 2,
    weights: dict[Card, float] | None = None,
    defensive: bool = False,
) -> int:
    """Run N draw simulations for one option ("deck" or "discard").

    Returns total points across all sims.
    """
    total = 0
    for i in range(n_sims):
        if samples is not None:
            opp_hand, sim_deck = samples[i]
        else:
            opp_hand, sim_deck = _sample_state(unknown, opponent_known, weights)

        if option == "discard":
            sim_hand = list(my_hand) + [discard_top]
            discard_card = rollout_ai.decide_discard(Hand(sim_hand))
            sim_hand_after = [c for c in sim_hand if c != discard_card]
            sim_discard_after = [discard_card]
        else:  # deck
            deck_copy = list(sim_deck)
            if not deck_copy:
                continue
            drawn_card = deck_copy.pop()
            sim_hand = list(my_hand) + [drawn_card]
            discard_card = rollout_ai.decide_discard(Hand(sim_hand))
            sim_hand_after = [c for c in sim_hand if c != discard_card]
            sim_discard_after = list(sim_discard_base) + [discard_card]
            sim_deck = deck_copy  # use the deck with drawn card removed

        result = rollout(
            list(sim_hand_after),
            list(opp_hand),
            list(sim_deck),
            list(sim_discard_after),
            False,
            rollout_ai,
            max_turns,
            knock_threshold,
            gin_bonus,
            undercut_bonus,
            min_deck_cards,
            defensive,
        )
        total += result.my_points
    return total


def _discard_sim_batch(
    cards: list[Card],
    card_to_discard: Card,
    rollout_ai: BasicAI,
    max_turns: int,
    knock_threshold: int,
    gin_bonus: int,
    undercut_bonus: int,
    n_sims: int,
    samples: list[tuple[list[Card], list[Card]]] | None,
    unknown: list[Card] | None,
    opponent_known: list[Card] | None,
    min_deck_cards: int = 2,
    weights: dict[Card, float] | None = None,
    evaluate_knock: bool = False,
    defensive: bool = False,
) -> tuple[int, int]:
    """Run N simulations for one candidate discard.

    Always evaluates the "continue" branch (discard, opponent moves next).
    With evaluate_knock, also scores the "knock now" branch against the
    same samples so the caller can choose the (discard, knock) pair jointly.

    Returns:
        (continue_total, knock_total). knock_total is 0 when not evaluated.
    """
    sim_hand = [c for c in cards if c != card_to_discard]
    total = 0
    knock_total = 0
    for i in range(n_sims):
        if samples is not None:
            opp_hand, sim_deck = samples[i]
        else:
            opp_hand, sim_deck = _sample_state(unknown, opponent_known, weights)

        if evaluate_knock:
            points, _, _ = score_knock(
                sim_hand,
                list(opp_hand),
                gin_bonus,
                undercut_bonus,
                knock_threshold,
            )
            knock_total += points

        sim_discard = [card_to_discard]
        result = rollout(
            list(sim_hand),
            list(opp_hand),
            list(sim_deck),
            list(sim_discard),
            False,
            rollout_ai,
            max_turns,
            knock_threshold,
            gin_bonus,
            undercut_bonus,
            min_deck_cards,
            defensive,
        )
        total += result.my_points
    return total, knock_total


def _knock_sim_batch(
    option: str,
    my_hand: list[Card],
    rollout_ai: BasicAI,
    max_turns: int,
    knock_threshold: int,
    gin_bonus: int,
    undercut_bonus: int,
    n_sims: int,
    samples: list[tuple[list[Card], list[Card]]] | None,
    unknown: list[Card] | None,
    opponent_known: list[Card] | None,
    pending_discard: Card | None = None,
    min_deck_cards: int = 2,
    weights: dict[Card, float] | None = None,
    defensive: bool = False,
) -> int:
    """Run N knock simulations for one option ("knock" or "continue").

    Returns total points across all sims.
    """
    total = 0
    for i in range(n_sims):
        if samples is not None:
            opp_hand, sim_deck = samples[i]
        else:
            opp_hand, sim_deck = _sample_state(unknown, opponent_known, weights)

        if option == "knock":
            points, _, _ = score_knock(
                my_hand,
                list(opp_hand),
                gin_bonus,
                undercut_bonus,
                knock_threshold,
            )
            total += points
        else:  # continue
            # Declining the knock means our discard goes on the pile and the
            # OPPONENT moves next - not us. Simulating my_turn=True with an
            # empty pile granted a phantom extra turn and hid our discard
            # from the opponent, inflating the value of continuing.
            sim_discard = [pending_discard] if pending_discard else []
            result = rollout(
                list(my_hand),
                list(opp_hand),
                list(sim_deck),
                sim_discard,
                False,
                rollout_ai,
                max_turns,
                knock_threshold,
                gin_bonus,
                undercut_bonus,
                min_deck_cards,
                defensive,
            )
            total += result.my_points
    return total
