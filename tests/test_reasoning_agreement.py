"""Each plain decision method must choose exactly what its *_with_reasoning twin chooses.

Positions are generated from seeded random deals. Every comparison uses a
fresh AI instance for each side (the AIs keep state such as the current
context between calls) and feeds both sides the same opponent events so the
opponent-model branches are exercised. MonteCarloAI is excluded because its
worker processes reseed randomly.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from gin_rummy.ai import BasicAI, ContextAwareAI, StatisticalAI
from gin_rummy.config import Config
from gin_rummy.game import Game
from gin_rummy.models import Card, Hand

STATS = Path(__file__).resolve().parent.parent / "models" / "statistical_ai_backup.json"
N_POSITIONS = 150


def _positions():
    """Yield (seed, game, ai_idx, opponent_events) for realistic mid-hand positions."""
    for seed in range(N_POSITIONS):
        rng = random.Random(seed)
        random.seed(seed)
        game = Game("A", "B")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        # Play a few plain turns so the discard pile and pickups are realistic
        driver = BasicAI(Config())
        for _ in range(rng.randint(0, 8)):
            if game.phase.name != "DRAWING" or len(game.deck) < 6:
                break
            p = game.current_player
            if driver.decide_draw(p.hand, game.top_of_discard).name == "DISCARD":
                game.draw_from_discard()
            else:
                game.draw_from_deck()
            game.discard(driver.decide_discard(p.hand))
        if game.phase.name != "DRAWING":
            continue
        events = [("discard", c) for c in game._discard_history[-3:]]
        if game.top_of_discard is not None and rng.random() < 0.5:
            events.append(("pickup", game.top_of_discard))
        yield seed, game, game.current_player_idx, events


def _fresh(kind: str, config: Config):
    if kind == "basic":
        return BasicAI(config)
    if kind == "context":
        return ContextAwareAI(config)
    if kind == "statistical":
        return StatisticalAI(stats_path=str(STATS), config=config)
    raise ValueError(kind)


def _prepared(kind: str, config: Config, events) -> BasicAI:
    ai = _fresh(kind, config)
    for what, card in events:
        (ai.record_opponent_discard if what == "discard" else ai.record_opponent_pickup)(card)
    return ai


@pytest.fixture(scope="module")
def config() -> Config:
    cfg = Config()
    cfg.ai.knock_strategy = "conservative"
    cfg.ai.conservative_knock_threshold = 6
    return cfg


@pytest.mark.parametrize("kind", ["basic", "context", "statistical"])
def test_plain_and_reasoning_twins_agree(kind: str, config: Config):
    disagreements: list[str] = []
    for seed, game, idx, events in _positions():
        ctx = game.get_game_context(idx)
        hand = game.players[idx].hand
        top = game.top_of_discard

        # draw (10 cards)
        random.seed(seed)
        plain = _prepared(kind, config, events).decide_draw(hand, top, ctx)
        random.seed(seed)
        reasoned = _prepared(kind, config, events).decide_draw_with_reasoning(hand, top, ctx)
        if plain != reasoned.choice:
            disagreements.append(f"seed {seed} draw: {plain.name} vs {reasoned.choice.name}")

        # discard (11 cards)
        eleven = Hand(list(hand) + [game.deck._cards[0] if hasattr(game.deck, "_cards") else game.deck.peek()])
        random.seed(seed)
        plain_card = _prepared(kind, config, events).decide_discard(eleven, ctx)
        random.seed(seed)
        reasoned_card = _prepared(kind, config, events).decide_discard_with_reasoning(eleven, ctx)
        if plain_card != reasoned_card.card:
            disagreements.append(f"seed {seed} discard: {plain_card} vs {reasoned_card.card}")

        # knock (10 cards)
        pending: Card = plain_card
        random.seed(seed)
        plain_knock = _prepared(kind, config, events).should_knock(hand, ctx, pending_discard=pending)
        random.seed(seed)
        reasoned_knock = _prepared(kind, config, events).should_knock_with_reasoning(hand, ctx, pending_discard=pending)
        if plain_knock != reasoned_knock.should_knock:
            disagreements.append(f"seed {seed} knock: {plain_knock} vs {reasoned_knock.should_knock}")

    assert not disagreements, f"{len(disagreements)} disagreements:\n" + "\n".join(disagreements[:15])
