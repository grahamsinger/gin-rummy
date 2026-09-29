"""Sampling hidden state: partition the unknown cards into an opponent hand and a deck."""

from __future__ import annotations

import logging
import random

from gin_rummy.models import Card

logger = logging.getLogger(__name__)


def _sample_state(
    unknown: list[Card],
    opponent_known: list[Card],
    weights: dict[Card, float] | None = None,
) -> tuple[list[Card], list[Card]]:
    """Standalone sampling: partition unknown cards into opp hand + deck.

    With `weights`, the opponent-hand fill is drawn by weighted sampling
    without replacement (Efraimidis-Spirakis: key = u^(1/w), take the top
    keys), so cards the opponent plausibly holds appear in their sampled
    hand more often. Without weights, sampling is uniform.

    Returns:
        (opponent_hand, deck)
    """
    opp_hand_size = 10
    fill_needed = max(0, opp_hand_size - len(opponent_known))
    fill_needed = min(fill_needed, len(unknown))

    if weights:
        keyed = sorted(
            unknown,
            key=lambda c: random.random() ** (1.0 / weights.get(c, 1.0)),
            reverse=True,
        )
        opp_fill = keyed[:fill_needed]
        deck = keyed[fill_needed:]
        random.shuffle(deck)  # deck order must stay uniform
    else:
        shuffled = list(unknown)
        random.shuffle(shuffled)
        opp_fill = shuffled[:fill_needed]
        deck = shuffled[fill_needed:]

    opp_hand = list(opponent_known) + opp_fill
    return opp_hand, deck
