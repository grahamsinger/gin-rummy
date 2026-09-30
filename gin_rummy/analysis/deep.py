"""Deep analysis of one decision.

Every option is played to the end of the hand against the same set of
possible hidden cards, under more than one playing style, until the
options can be told apart or the sample budget is spent. The analysis
only uses what the player can know; the real hidden cards are played
once per option and reported separately."""

from __future__ import annotations

import math
import multiprocessing
import random
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from gin_rummy.ai.mc.rollout import score_knock
from gin_rummy.analysis.playout import ENDINGS, Outcome, Rules, meld_names, play_out
from gin_rummy.analysis.style import ALL_CARDS, GIN_HUNTER, GREEDY, PATIENT, Style, choose_discard, live_outs
from gin_rummy.game import Game
from gin_rummy.models import Card, analyze_hand

Sample = tuple[list[Card], list[Card]]  # (opponent hand, deck)

DEFAULT_STYLES: tuple[Style, ...] = (PATIENT, GREEDY, GIN_HUNTER)  # the first is the main one
CLEAR_Z = 3.0  # standard errors between two options for the gap to count as settled
DROP_Z = 4.0  # an option this far behind the leader is not sampled further


@dataclass(frozen=True)
class Position:
    """A decision as the player sees it, plus (when known) the real hidden cards."""

    decision: str  # draw | discard | knock
    hand: tuple[Card, ...]  # draw: 10 cards; discard: 11; knock: the 10 kept
    public: frozenset[Card]  # every face-up card seen so far that is not in the hand
    opponent_known: tuple[Card, ...] = ()  # cards the opponent took from the pile and still holds
    discard_top: Card | None = None  # draw: the card on offer
    blocked: Card | None = None  # discard: the card just taken from the pile
    pending_discard: Card | None = None  # knock: the card being thrown
    rules: Rules = field(default_factory=Rules)
    seed: int | None = None
    actual: Sample | None = None

    @property
    def unknown(self) -> list[Card]:
        gone = set(self.hand) | self.public
        if self.pending_discard is not None:
            gone.add(self.pending_discard)
        return [c for c in ALL_CARDS if c not in gone]

    @property
    def key(self) -> str:
        """Identifies the position: same decision, hand and visible cards give the same key."""
        parts = [
            self.decision,
            " ".join(c.code for c in sorted(self.hand)),
            " ".join(c.code for c in sorted(self.public)),
            " ".join(c.code for c in sorted(self.opponent_known)),
            self.discard_top.code if self.discard_top else "-",
            self.pending_discard.code if self.pending_discard else "-",
        ]
        return "|".join(parts)

    def options(self) -> list[str]:
        if self.decision == "draw":
            return ["deck", "pile"]
        if self.decision == "knock":
            return ["knock", "continue"]
        return [c.code for c in sorted(self.hand) if c != self.blocked]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "seed": self.seed,
            "hand": [c.code for c in sorted(self.hand)],
            "public": [c.code for c in sorted(self.public)],
            "opponent_known": [c.code for c in self.opponent_known],
            "discard_top": self.discard_top.code if self.discard_top else None,
            "blocked": self.blocked.code if self.blocked else None,
            "pending_discard": self.pending_discard.code if self.pending_discard else None,
            "deck_size": len(self.unknown) - (10 - len(self.opponent_known)),
        }


def position_from_game(
    game: Game, seat: int, decision: str, seed: int | None = None, pending_discard: Card | None = None
) -> Position:
    """The position `seat` faces in `game`, with the real hidden cards attached."""
    ctx = game.get_game_context(seat)
    hand = [c for c in game.players[seat].hand if c != pending_discard]
    known = ctx.known_cards
    opponent_known = sorted(known.opponent_hand_known) if known else []
    public = set(ctx.discard_history) | set(game.discard_pile) | set(opponent_known)
    public -= set(game.players[seat].hand)
    deck = list(game.deck)  # bottom first: drawn from the end, as in a play-out
    return Position(
        decision=decision,
        hand=tuple(hand),
        public=frozenset(public),
        opponent_known=tuple(opponent_known),
        discard_top=game.top_of_discard if decision == "draw" else None,
        blocked=game.discard_blocked_card if decision == "discard" else None,
        pending_discard=pending_discard,
        rules=Rules(game.knock_threshold, game.gin_bonus, game.undercut_bonus, game.min_deck_cards),
        seed=seed,
        actual=(list(game.players[1 - seat].hand), deck),
    )


def draw_samples(position: Position, n: int, rng: random.Random) -> list[Sample]:
    """Deal the unseen cards `n` ways: the opponent's unknown cards, then the deck in order."""
    unknown = position.unknown
    fill = 10 - len(position.opponent_known)
    samples = []
    for _ in range(n):
        cards = list(unknown)
        rng.shuffle(cards)
        samples.append(([*position.opponent_known, *cards[:fill]], cards[fill:]))
    return samples


def play_option(position: Position, option: str, sample: Sample, style: Style) -> Outcome:
    """Make the move `option` against one deal of the hidden cards and play the hand out."""
    opp_hand, deck = sample
    hand = list(position.hand)
    public = set(position.public)
    rules = position.rules

    if position.decision == "knock":
        if option == "knock":
            points, is_gin, is_undercut = score_knock(
                hand, list(opp_hand), rules.gin_bonus, rules.undercut_bonus, rules.knock_threshold
            )
            ending = "my_gin" if is_gin else "my_knock_undercut" if is_undercut else "my_knock"
            return Outcome(points, ending, 0, meld_names(hand), False)
        discard = position.pending_discard
        assert discard is not None
    elif position.decision == "draw":
        top = position.discard_top
        assert top is not None
        if option == "pile":
            hand.append(top)
            public.discard(top)
            discard = choose_discard(hand, public, style, blocked=top)
        else:
            deck = list(deck)
            hand.append(deck.pop())
            discard = choose_discard(hand, public, style, blocked=None)
        hand.remove(discard)
    else:
        discard = Card.parse(option)
        hand.remove(discard)

    public.add(discard)
    return play_out(hand, opp_hand, deck, [discard], public, False, style, style, rules)


def run_batch(position: Position, option: str, style: Style, samples: list[Sample]) -> dict[str, Any]:
    """Worker task: play one option against a batch of samples."""
    points = []
    endings: Counter[str] = Counter()
    melds: Counter[str] = Counter()
    turns = 0
    taken = 0
    for sample in samples:
        outcome = play_option(position, option, sample, style)
        points.append(outcome.points)
        endings[outcome.ending] += 1
        melds.update(outcome.my_melds)
        turns += outcome.turns
        taken += outcome.first_discard_taken
    return {"points": points, "endings": endings, "melds": melds, "turns": turns, "taken": taken}


@dataclass
class _Tally:
    """Everything gathered for one option under one style."""

    points: list[int] = field(default_factory=list)
    endings: Counter = field(default_factory=Counter)
    melds: Counter = field(default_factory=Counter)
    turns: int = 0
    taken: int = 0

    def add(self, batch: dict[str, Any]) -> None:
        self.points.extend(batch["points"])
        self.endings.update(batch["endings"])
        self.melds.update(batch["melds"])
        self.turns += batch["turns"]
        self.taken += batch["taken"]


def _mean_se(values: list[int] | list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var / n)


def _gap(leader: list[int], other: list[int]) -> tuple[float, float]:
    """Mean and standard error of leader minus other over the samples both have played."""
    n = min(len(leader), len(other))
    return _mean_se([a - b for a, b in zip(leader[:n], other[:n], strict=True)])


def _verdict(gap: float, se: float) -> str:
    if se == 0:
        return "clear" if gap > 0 else "level"
    z = gap / se
    if z >= CLEAR_Z:
        return "clear"
    if z >= 2.0:
        return "likely"
    return "too close to call"


def _summarise(option: str, tally: _Tally, leader: _Tally, start_melds: set[str]) -> dict[str, Any]:
    n = len(tally.points)
    mean, se = _mean_se(tally.points)
    gap, gap_se = _gap(leader.points, tally.points)
    new_melds = [(m, c) for m, c in tally.melds.most_common() if m not in start_melds]
    return {
        "option": option,
        "samples": n,
        "points": round(mean, 2),
        "points_se": round(se, 2),
        "behind_leader": round(gap, 2),
        "behind_leader_se": round(gap_se, 2),
        "win_rate": round(sum(p > 0 for p in tally.points) / n, 4) if n else 0,
        "endings": {e: round(tally.endings[e] / n, 4) for e in ENDINGS if tally.endings[e]} if n else {},
        "turns": round(tally.turns / n, 1) if n else 0,
        "discard_taken": round(tally.taken / n, 4) if n else 0,
        "new_melds": [{"meld": m, "rate": round(c / n, 4)} for m, c in new_melds[:4]],
    }


def describe_options(position: Position) -> dict[str, dict[str, Any]]:
    """For a discard: what each option leaves behind (deadwood now, cards that would meld)."""
    if position.decision != "discard":
        return {}
    described = {}
    for option in position.options():
        kept = [c for c in position.hand if c.code != option]
        outs = live_outs(kept, position.public | {Card.parse(option)})
        described[option] = {
            "deadwood_after": analyze_hand(kept).deadwood_value,
            "outs": [{"card": c.code, "saves": s} for c, s in sorted(outs, key=lambda o: -o[1])],
        }
    return described


def analyse(
    position: Position,
    styles: tuple[Style, ...] = DEFAULT_STYLES,
    max_samples: int = 20000,
    batch: int = 2000,
    workers: int = 0,
    sample_seed: int = 0,
    pool: Executor | None = None,
    progress: Callable[[str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Play every option out until the best one is clear or `max_samples` deals have been tried.

    Sampling is in rounds of `batch` deals shared by every option and
    style. After each round an option that is DROP_Z standard errors
    behind the leader under every style is set aside, and the analysis
    stops once the leader is CLEAR_Z ahead of all the others.
    """
    started = time.time()
    rng = random.Random(sample_seed)
    options = position.options()
    tallies = {s.name: {o: _Tally() for o in options} for s in styles}
    alive = list(options)
    own_pool = pool is None
    if pool is None:
        n_workers = workers or max(1, (multiprocessing.cpu_count() or 2) - 1)
        pool = ProcessPoolExecutor(max_workers=n_workers, mp_context=multiprocessing.get_context("spawn"))
    else:
        n_workers = workers or 8

    def leader_of(style: Style) -> str:
        return max(alive, key=lambda o: _mean_se(tallies[style.name][o].points)[0])

    drawn = 0
    settled = False
    try:
        while drawn < max_samples and not settled:
            if should_stop is not None and should_stop():
                break
            samples = draw_samples(position, min(batch, max_samples - drawn), rng)
            drawn += len(samples)
            chunk = max(1, math.ceil(len(samples) / n_workers))
            futures = []
            for style in styles:
                for option in alive:
                    for i in range(0, len(samples), chunk):
                        future = pool.submit(run_batch, position, option, style, samples[i : i + chunk])
                        futures.append((style.name, option, future))
            for style_name, option, future in futures:
                tallies[style_name][option].add(future.result())

            # An option stays while any style still has it within reach of that style's leader
            settled = True
            keep = set()
            for style in styles:
                lead = leader_of(style)
                keep.add(lead)
                for option in alive:
                    if option == lead:
                        continue
                    gap, se = _gap(tallies[style.name][lead].points, tallies[style.name][option].points)
                    z = gap / se if se else float("inf")
                    if z < DROP_Z:
                        keep.add(option)
                    if z < CLEAR_Z:
                        settled = False
            alive = [o for o in alive if o in keep]
            if progress:
                lead = leader_of(styles[0])
                progress(f"{drawn} deals: {len(alive)} option(s) still in contention, {lead} leads")
    finally:
        if own_pool:
            pool.shutdown()

    start_melds = set(meld_names(list(position.hand)))
    by_style = [_style_report(position, style, tallies[style.name], start_melds) for style in styles]
    best = by_style[0]["best"]
    for report in by_style:
        row = next(r for r in report["options"] if r["option"] == best)
        report["main_best"] = _standing(row["behind_leader"], row["behind_leader_se"])

    return {
        "position": position.to_dict(),
        "position_key": position.key,
        "best": best,
        "confidence": by_style[0]["confidence"],
        "level_with": by_style[0]["level_with"],
        "styles_agree": all(report["main_best"] != "behind" for report in by_style),
        "samples": drawn,
        "seconds": round(time.time() - started, 1),
        "sample_seed": sample_seed,
        "option_notes": describe_options(position),
        "styles": by_style,
    }


def _standing(gap: float, se: float) -> str:
    """Where an option stands against a style's leader: best, level (within noise) or behind."""
    if gap == 0:
        return "best"
    return "behind" if se == 0 or gap / se >= 2.0 else "level"


def _style_report(
    position: Position, style: Style, tallies: dict[str, _Tally], start_melds: set[str]
) -> dict[str, Any]:
    options = position.options()
    lead = max(options, key=lambda o: _mean_se(tallies[o].points)[0])
    rows = [_summarise(o, tallies[o], tallies[lead], start_melds) for o in options]
    rows.sort(key=lambda r: -r["points"])
    runner_up = rows[1] if len(rows) > 1 else None
    confidence = _verdict(runner_up["behind_leader"], runner_up["behind_leader_se"]) if runner_up else "clear"
    actual = None
    if position.actual is not None:
        actual = {}
        for option in options:
            outcome = play_option(position, option, position.actual, style)
            actual[option] = {"points": outcome.points, "ending": outcome.ending, "turns": outcome.turns}
    return {
        "style": style.name,
        "patience": style.patience,
        "knock_at": style.knock_at,
        "best": lead,
        "confidence": confidence,
        "level_with": [
            r["option"] for r in rows[1:] if _standing(r["behind_leader"], r["behind_leader_se"]) == "level"
        ],
        "options": rows,
        "actual_deal": actual,
    }
