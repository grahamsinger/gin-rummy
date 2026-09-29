"""Simulation batches, the unit of work sent to worker processes."""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass

from gin_rummy.ai.basic import BasicAI
from gin_rummy.ai.mc.rollout import rollout, score_knock
from gin_rummy.ai.mc.sampling import _sample_state
from gin_rummy.models import Card, Hand

logger = logging.getLogger(__name__)


def worker_init() -> None:
    """Seed random uniquely per worker process."""
    seed = os.getpid() * 31 + int(time.time() * 1000) % 1_000_000
    random.seed(seed)


Sample = tuple[list[Card], list[Card]]  # (opponent hand, deck)


@dataclass(frozen=True)
class SimParams:
    """Everything a simulation batch needs apart from the option it evaluates.

    Built once per decision and sent to the workers with each task. In
    paired mode `samples` holds the pre-drawn (opponent hand, deck) pairs
    shared by every option; otherwise each simulation draws its own from
    `unknown` / `opponent_known` (weighted by `weights` when given).
    """

    rollout_ai: BasicAI
    n_sims: int
    max_turns: int
    knock_threshold: int
    gin_bonus: int
    undercut_bonus: int
    min_deck_cards: int
    defensive: bool
    samples: list[Sample] | None
    unknown: list[Card] | None
    opponent_known: list[Card] | None
    weights: dict[Card, float] | None

    def sample(self, i: int) -> Sample:
        """The i-th hidden-state sample: shared in paired mode, fresh otherwise."""
        if self.samples is not None:
            return self.samples[i]
        return _sample_state(self.unknown or [], self.opponent_known or [], self.weights)

    def rollout(self, my_hand: list[Card], opp_hand: list[Card], deck: list[Card], pile: list[Card]) -> int:
        """Play the position forward with the opponent to move; my points."""
        result = rollout(
            list(my_hand),
            list(opp_hand),
            list(deck),
            list(pile),
            False,
            self.rollout_ai,
            self.max_turns,
            self.knock_threshold,
            self.gin_bonus,
            self.undercut_bonus,
            self.min_deck_cards,
            self.defensive,
        )
        return result.my_points

    def knock_points(self, my_hand: list[Card], opp_hand: list[Card]) -> int:
        """My points for knocking now against this opponent hand."""
        points, _, _ = score_knock(my_hand, list(opp_hand), self.gin_bonus, self.undercut_bonus, self.knock_threshold)
        return points


def _draw_sim_batch(
    params: SimParams,
    option: str,
    my_hand: list[Card],
    discard_top: Card,
    sim_discard_base: list[Card],
) -> int:
    """Run N draw simulations for one option ("deck" or "discard").

    Returns total points across all sims.
    """
    total = 0
    for i in range(params.n_sims):
        opp_hand, sim_deck = params.sample(i)

        if option == "discard":
            sim_hand = list(my_hand) + [discard_top]
            discard_card = params.rollout_ai.decide_discard(Hand(sim_hand))
            sim_hand_after = [c for c in sim_hand if c != discard_card]
            sim_discard_after = [discard_card]
        else:  # deck
            deck_copy = list(sim_deck)
            if not deck_copy:
                continue
            drawn_card = deck_copy.pop()
            sim_hand = list(my_hand) + [drawn_card]
            discard_card = params.rollout_ai.decide_discard(Hand(sim_hand))
            sim_hand_after = [c for c in sim_hand if c != discard_card]
            sim_discard_after = list(sim_discard_base) + [discard_card]
            sim_deck = deck_copy  # use the deck with drawn card removed

        total += params.rollout(sim_hand_after, opp_hand, sim_deck, sim_discard_after)
    return total


def _discard_sim_batch(
    params: SimParams,
    cards: list[Card],
    card_to_discard: Card,
    evaluate_knock: bool = False,
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
    for i in range(params.n_sims):
        opp_hand, sim_deck = params.sample(i)

        if evaluate_knock:
            knock_total += params.knock_points(sim_hand, opp_hand)

        total += params.rollout(sim_hand, opp_hand, sim_deck, [card_to_discard])
    return total, knock_total


def _knock_sim_batch(
    params: SimParams,
    option: str,
    my_hand: list[Card],
    pending_discard: Card | None = None,
) -> int:
    """Run N knock simulations for one option ("knock" or "continue").

    Returns total points across all sims.
    """
    total = 0
    for i in range(params.n_sims):
        opp_hand, sim_deck = params.sample(i)

        if option == "knock":
            total += params.knock_points(my_hand, opp_hand)
        else:  # continue
            # Declining the knock means our discard goes on the pile and the
            # OPPONENT moves next - not us. Simulating my_turn=True with an
            # empty pile granted a phantom extra turn and hid our discard
            # from the opponent, inflating the value of continuing.
            sim_discard = [pending_discard] if pending_discard else []
            total += params.rollout(my_hand, opp_hand, sim_deck, sim_discard)
    return total
