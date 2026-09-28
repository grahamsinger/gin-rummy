"""Turn recording shared by every UI (CLI, web).

The tracker (`database.GameTracker`) knows how to write rows. This module
knows how to turn what happened in a turn into those rows, so the CLI and
the web session no longer carry their own copies of that mapping.

Usage::

    recorder = TurnRecorder(tracker)
    snapshot = TurnSnapshot.of(player)          # before the draw
    ...                                         # play the turn
    recorder.write(TurnRecord.from_actions(player, snapshot, actions))   # AI turn
    recorder.write(TurnRecord.human(player, snapshot, "deck", drawn, discarded, did_knock=False))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gin_rummy.ai import DrawChoice, TurnReasoning
from gin_rummy.config import get_config

if TYPE_CHECKING:
    from gin_rummy.database import GameTracker
    from gin_rummy.game_runner import TurnActions
    from gin_rummy.models import Card, Player


@dataclass(frozen=True)
class TurnSnapshot:
    """A player's hand as it was before the turn's draw."""

    cards_before: list[str]
    deadwood_before: int

    @classmethod
    def of(cls, player: Player) -> TurnSnapshot:
        return cls([c.code for c in player.hand], player.hand.deadwood_total)


@dataclass
class TurnRecord:
    """Everything the `turns` table (and `ai_decisions`) needs for one turn."""

    player_name: str
    drew_from: str  # "deck" | "discard"
    card_drawn: str
    card_discarded: str
    did_knock: bool
    cards_before: list[str]
    cards_after: list[str]
    deadwood_before: int
    deadwood_after: int
    reasoning: TurnReasoning | None = None

    @classmethod
    def from_actions(cls, player: Player, snapshot: TurnSnapshot, actions: TurnActions) -> TurnRecord:
        """Build the record for an AI turn from the runner's TurnActions.

        The player's hand is already post-discard (10 cards); the filter only
        matters if a caller passes an 11-card hand.
        """
        return cls(
            player_name=player.name,
            drew_from="discard" if actions.draw_source == DrawChoice.DISCARD else "deck",
            card_drawn=actions.drawn_card.code,
            card_discarded=actions.discarded_card.code,
            did_knock=actions.did_knock,
            cards_before=snapshot.cards_before,
            cards_after=[c.code for c in player.hand if c != actions.discarded_card],
            deadwood_before=snapshot.deadwood_before,
            deadwood_after=actions.deadwood_after,
            reasoning=actions.reasoning,
        )

    @classmethod
    def human(
        cls,
        player: Player,
        snapshot: TurnSnapshot,
        drew_from: str,
        card_drawn: Card,
        card_discarded: Card,
        *,
        did_knock: bool,
    ) -> TurnRecord:
        """Build the record for a human turn; call after the discard (or knock)."""
        return cls(
            player_name=player.name,
            drew_from=drew_from,
            card_drawn=card_drawn.code,
            card_discarded=card_discarded.code,
            did_knock=did_knock,
            cards_before=snapshot.cards_before,
            cards_after=[c.code for c in player.hand],
            deadwood_before=snapshot.deadwood_before,
            deadwood_after=player.hand.deadwood_total,
        )


class TurnRecorder:
    """Writes TurnRecords through a GameTracker. A None tracker makes it a no-op."""

    def __init__(self, tracker: GameTracker | None, track_ai_decisions: bool | None = None) -> None:
        self.tracker = tracker
        if track_ai_decisions is None:
            track_ai_decisions = get_config().database.track_ai_decisions
        self.track_ai_decisions = track_ai_decisions

    def write(self, record: TurnRecord) -> int | None:
        """Record the turn (and its AI reasoning, if any). Returns the turn id."""
        if self.tracker is None:
            return None
        turn_id = self.tracker.record_turn(
            player_name=record.player_name,
            drew_from=record.drew_from,
            card_drawn=record.card_drawn,
            card_discarded=record.card_discarded,
            did_knock=record.did_knock,
            cards_before=record.cards_before,
            cards_after=record.cards_after,
            deadwood_before=record.deadwood_before,
            deadwood_after=record.deadwood_after,
        )
        if record.reasoning is not None and self.track_ai_decisions:
            self._write_reasoning(turn_id, record.reasoning)
        return turn_id

    def _write_reasoning(self, turn_id: int, reasoning: TurnReasoning) -> None:
        assert self.tracker is not None
        if reasoning.draw:
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type="draw",
                choice=reasoning.draw.choice.name,
                reasoning=reasoning.draw.reasoning,
                options_considered=reasoning.draw.factors,
            )
        if reasoning.discard:
            options = reasoning.discard.factors.copy()
            for card_str, dw in reasoning.discard.options_considered:
                options.append(f"{card_str} → dw={dw}")
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type="discard",
                choice=reasoning.discard.card.code,  # same ASCII format as every other card column
                reasoning=reasoning.discard.reasoning,
                options_considered=options,
            )
        if reasoning.knock:
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type="knock",
                choice="knock" if reasoning.knock.should_knock else "no_knock",
                reasoning=reasoning.knock.reasoning,
                options_considered=reasoning.knock.factors,
            )
