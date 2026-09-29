"""What MonteCarloAI was thinking: typed per-decision data, and its display text.

MonteCarloAI fills one MCThinking per turn. The web UI receives it as a
dict (to_dict, same keys as before it was typed), the scenario quiz reads
the discard candidates, and the *_with_reasoning twins format it here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from gin_rummy.ai.types import DiscardReasoning, DrawChoice, DrawReasoning, KnockReasoning
from gin_rummy.models import Card


@dataclass
class DrawThinking:
    deck_avg_points: float
    deck_sims: int
    discard_avg_points: float
    discard_sims: int
    discard_card: str
    choice: str  # "deck" or "discard"
    advantage: float
    fallback: bool


@dataclass
class DiscardCandidate:
    card: str
    avg_points: float
    sims: int
    deadwood_after: int
    knock_avg_points: float | None = None  # set when the knock branch was evaluated jointly
    continue_avg_points: float | None = None


@dataclass
class DiscardThinking:
    candidates: list[DiscardCandidate]  # best first
    chosen: str
    hand_size: int
    deadwood_count: int
    fallback: bool
    min_advantage: float
    joint_evaluation: bool


@dataclass
class KnockThinking:
    chose_knock: bool
    deadwood: int
    knock_avg_points: float | None = None
    continue_avg_points: float | None = None
    advantage: float | None = None
    fallback: bool = False
    reason: str | None = None  # "gin", "deck_nearly_empty" or "joint_plan" when no fresh simulation ran


@dataclass
class MCThinking:
    """The three decisions of one turn; None where a decision was not simulated."""

    draw: DrawThinking | None = None
    discard: DiscardThinking | None = None
    knock: KnockThinking | None = None
    _keys: tuple[str, ...] = field(default=("draw", "discard", "knock"), init=False, repr=False, compare=False)

    def clear(self, key: str) -> None:
        assert key in self._keys, key
        setattr(self, key, None)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form for the web UI (same keys as the old dicts)."""
        return {k: asdict(v) if v is not None else None for k, v in ((key, getattr(self, key)) for key in self._keys)}


# ---- Display text for the *_with_reasoning twins ----


def draw_reasoning(choice: DrawChoice, thinking: MCThinking | None) -> DrawReasoning:
    factors: list[str] = []
    dt = thinking.draw if thinking else None
    if dt is not None:
        factors.append(f"MC draw sims: {dt.deck_sims}")
        factors.append(f"DECK avg: {dt.deck_avg_points}")
        factors.append(f"DISCARD avg: {dt.discard_avg_points}")
        if dt.discard_card:
            factors.append(f"Discard card: {dt.discard_card}")
        reasoning = (
            f"MC: DECK avg={dt.deck_avg_points}, DISCARD({dt.discard_card or '?'}) avg={dt.discard_avg_points} "
            f"-> {choice.name}"
        )
    else:
        reasoning = f"Drew from {choice.name} (fallback)"
    return DrawReasoning(choice=choice, reasoning=reasoning, factors=factors)


def discard_reasoning(card: Card, thinking: MCThinking | None) -> DiscardReasoning:
    factors: list[str] = []
    options: list[tuple[str, int]] = []
    dd = thinking.discard if thinking else None
    if dd is not None:
        factors.append(f"MC discard candidates: {len(dd.candidates)}")
        factors.append(f"Deadwood cards: {dd.deadwood_count}")
        for cand in dd.candidates:
            options.append((cand.card, cand.deadwood_after))
            factors.append(f"{cand.card}: avg={cand.avg_points}, dw={cand.deadwood_after}")
        reasoning = f"MC: chose {dd.chosen} from {len(dd.candidates)} candidates"
    else:
        reasoning = f"Discarded {card} (fallback)"
    return DiscardReasoning(card=card, reasoning=reasoning, factors=factors, options_considered=options)


def knock_reasoning(result: bool, hand_deadwood: int, thinking: MCThinking | None) -> KnockReasoning:
    factors: list[str] = []
    score: float | None = None
    kt = thinking.knock if thinking else None
    if kt is not None:
        factors.append(f"Deadwood: {kt.deadwood}")
        if kt.reason:
            factors.append(f"Reason: {kt.reason}")
            reasoning = f"Knock ({kt.reason}): deadwood={kt.deadwood}"
        elif kt.knock_avg_points is not None:
            factors.append(f"MC knock avg: {kt.knock_avg_points}")
            factors.append(f"MC continue avg: {kt.continue_avg_points}")
            score = kt.knock_avg_points
            reasoning = (
                f"MC: knock avg={kt.knock_avg_points}, continue avg={kt.continue_avg_points} "
                f"-> {'KNOCK' if result else 'CONTINUE'}"
            )
        else:
            reasoning = f"{'Knocked' if result else 'No knock'}: deadwood={kt.deadwood}"
    else:
        factors.append(f"Deadwood: {hand_deadwood}")
        reasoning = f"{'Knocked' if result else 'No knock'}: deadwood={hand_deadwood} (fallback)"
    return KnockReasoning(should_knock=result, reasoning=reasoning, score=score, factors=factors)
