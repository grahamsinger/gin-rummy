"""Experiment: how fast are MonteCarloAI decisions across sims x workers?

Times each decision type (draw, discard, knock) on fixed representative
hands for every combination of simulation count and worker count, and
reports per-decision latency plus estimated full-turn time.

Usage:
    uv run python experiments/mc_timing.py
    uv run python experiments/mc_timing.py --sims 100,500 --workers 1,8 --reps 2
"""

import argparse
import random
import statistics
import time

from gin_rummy.ai.monte_carlo import MonteCarloAI
from gin_rummy.config import Config, MonteCarloAIConfig
from gin_rummy.context import GameContext, KnownCards
from gin_rummy.models import Card, Hand, Rank, Suit


def make_hand_11() -> Hand:
    """Mid-game 11-card hand: two melds forming, real discard candidates."""
    return Hand(
        [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.SEVEN, Suit.HEARTS),
            Card(Rank.EIGHT, Suit.HEARTS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.KING, Suit.DIAMONDS),
            Card(Rank.NINE, Suit.CLUBS),
        ]
    )


def make_hand_10() -> Hand:
    """Knock-eligible 10-card hand (deadwood 2)."""
    return Hand(
        [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FOUR, Suit.SPADES),
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.SEVEN, Suit.HEARTS),
            Card(Rank.EIGHT, Suit.HEARTS),
            Card(Rank.NINE, Suit.HEARTS),
            Card(Rank.TWO, Suit.HEARTS),
        ]
    )


def make_context(hand: Hand) -> GameContext:
    known_cards = KnownCards(
        my_hand=frozenset(hand),
        opponent_hand_known=frozenset({Card(Rank.QUEEN, Suit.CLUBS)}),
        discard_top=Card(Rank.SIX, Suit.DIAMONDS),
        discard_buried=frozenset(
            {
                Card(Rank.KING, Suit.CLUBS),
                Card(Rank.TEN, Suit.DIAMONDS),
            }
        ),
    )
    return GameContext(
        deck_remaining=20,
        deck_position_pct=1.0 - (20 / 31.0),
        my_score=25,
        opponent_score=30,
        target_score=100,
        known_cards=known_cards,
        discard_history=[
            Card(Rank.KING, Suit.CLUBS),
            Card(Rank.TEN, Suit.DIAMONDS),
            Card(Rank.SIX, Suit.DIAMONDS),
        ],
    )


def make_ai(sims: int, workers: int) -> MonteCarloAI:
    config = Config()
    config.monte_carlo_ai = MonteCarloAIConfig(
        draw_simulations=sims,
        discard_simulations=sims,
        knock_simulations=sims,
        max_workers=workers,
        sample_strategy="paired",
    )
    ai = MonteCarloAI(config)
    # Give the opponent model observations so weighted sampling is active
    ai.record_opponent_pickup(Card(Rank.QUEEN, Suit.CLUBS))
    ai.record_opponent_discard(Card(Rank.KING, Suit.CLUBS))
    return ai


def time_decision(fn, reps: int) -> list[float]:
    times = []
    for i in range(reps):
        random.seed(1000 + i)
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return times


def run_combo(sims: int, workers: int, reps: int) -> dict:
    ai = make_ai(sims, workers)
    hand11 = make_hand_11()
    hand10 = make_hand_10()
    ctx = make_context(hand11)
    ai._current_context = ctx
    discard_top = Card(Rank.SIX, Suit.DIAMONDS)

    # Warmup: spins up the process pool so its startup cost isn't timed
    random.seed(999)
    ai.decide_draw(hand11, discard_top, ctx)

    draw_times = time_decision(lambda: ai.decide_draw(hand11, discard_top, ctx), reps)

    def discard_fn():
        ai._turn_plan = None
        ai.decide_discard(hand11)

    discard_times = time_decision(discard_fn, reps)

    def knock_fn():
        ai._turn_plan = None  # force the full knock evaluation path
        ai.should_knock(hand10, ctx, pending_discard=Card(Rank.KING, Suit.DIAMONDS))

    knock_times = time_decision(knock_fn, reps)

    ai.shutdown()

    draw = statistics.median(draw_times)
    discard = statistics.median(discard_times)
    knock = statistics.median(knock_times)
    return {
        "sims": sims,
        "workers": workers,
        "draw_s": draw,
        "discard_s": discard,
        "knock_s": knock,
        "turn_s": draw + discard + knock,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sims", default="100,500,1000,2000", help="Comma-separated simulation counts")
    parser.add_argument("--workers", default="1,4,8,0", help="Comma-separated worker counts (0 = auto: cores-1)")
    parser.add_argument("--reps", type=int, default=3, help="Timed repetitions per decision (median reported)")
    args = parser.parse_args()

    sims_list = [int(s) for s in args.sims.split(",")]
    workers_list = [int(w) for w in args.workers.split(",")]

    import os

    auto = max(1, (os.cpu_count() or 2) - 1)
    print(f"CPU cores: {os.cpu_count()} (auto workers = {auto})")
    print(f"Reps per decision: {args.reps} (median reported)\n")

    header = f"{'sims':>6} {'workers':>8} {'draw':>9} {'discard':>9} {'knock':>9} {'turn':>9}"
    print(header)
    print("-" * len(header))

    results = []
    for sims in sims_list:
        for workers in workers_list:
            r = run_combo(sims, workers, args.reps)
            results.append(r)
            w_label = f"{workers}" if workers != 0 else f"auto({auto})"
            print(
                f"{sims:>6} {w_label:>8} "
                f"{r['draw_s'] * 1000:>7.0f}ms {r['discard_s'] * 1000:>7.0f}ms "
                f"{r['knock_s'] * 1000:>7.0f}ms {r['turn_s'] * 1000:>7.0f}ms"
            )

    print("\nturn = draw + discard + knock (one full AI turn, worst case)")
    print("Note: discard cost scales with deadwood candidates (fixed here);")
    print("knock timed on the standalone path (joint plan bypassed).")


if __name__ == "__main__":
    main()
