"""Tests for the learning module.

Note: These tests require the optional 'learning' dependencies.
Run with: uv sync --extra learning && uv run pytest tests/test_learning.py
"""

import random

import pytest

# Skip all tests if torch is not available
torch = pytest.importorskip("torch")
numpy = pytest.importorskip("numpy")

pytestmark = pytest.mark.learning

from gin_rummy.learning.models import DiscardNet, DrawNet, KnockNet, ModelPersistence
from gin_rummy.learning.replay import Experience, ReplayBuffer, batch_to_tensors
from gin_rummy.learning.rewards import RewardCalculator
from gin_rummy.learning.state import NUM_CARDS, StateEncoder
from gin_rummy.models import Card, Hand, Rank, Suit


class TestStateEncoder:
    """Tests for state encoding."""

    def test_card_to_index(self):
        """Test card to index conversion."""
        # Ace of Clubs should be 0
        ace_clubs = Card(Rank.ACE, Suit.CLUBS)
        assert ace_clubs.index == 0

        # King of Spades should be 51
        king_spades = Card(Rank.KING, Suit.SPADES)
        assert king_spades.index == 51

        # Ace of Diamonds should be 13
        ace_diamonds = Card(Rank.ACE, Suit.DIAMONDS)
        assert ace_diamonds.index == 13

    def test_encode_hand(self):
        """Test hand encoding produces correct shape and values."""
        encoder = StateEncoder()
        cards = [
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.KING, Suit.SPADES),
        ]
        hand = Hand(cards)

        encoding = encoder.encode_hand(hand)

        assert encoding.shape == (NUM_CARDS,)
        assert encoding.sum() == 3  # 3 cards in hand
        assert encoding[cards[0].index] == 1.0
        assert encoding[cards[1].index] == 1.0
        assert encoding[cards[2].index] == 1.0

    def test_encode_card(self):
        """Test single card encoding."""
        encoder = StateEncoder()
        card = Card(Rank.FIVE, Suit.DIAMONDS)

        encoding = encoder.encode_card(card)

        assert encoding.shape == (NUM_CARDS,)
        assert encoding.sum() == 1
        assert encoding[card.index] == 1.0

    def test_encode_card_none(self):
        """Test encoding None card produces zeros."""
        encoder = StateEncoder()
        encoding = encoder.encode_card(None)

        assert encoding.shape == (NUM_CARDS,)
        assert encoding.sum() == 0

    def test_encode_draw_state_shape(self):
        """Test draw state encoding produces correct shape."""
        encoder = StateEncoder()
        cards = [Card(Rank(r), Suit.CLUBS) for r in range(1, 11)]
        hand = Hand(cards)
        discard_top = Card(Rank.JACK, Suit.HEARTS)

        state = encoder.encode_draw_state(hand, discard_top, None, None)

        assert state.shape == (StateEncoder.DRAW_STATE_SIZE,)

    def test_encode_discard_state_shape(self):
        """Test discard state encoding produces correct shape."""
        encoder = StateEncoder()
        cards = [Card(Rank(r), Suit.CLUBS) for r in range(1, 12)]  # 11 cards
        hand = Hand(cards)
        drawn_card = Card(Rank.QUEEN, Suit.HEARTS)

        state = encoder.encode_discard_state(hand, drawn_card, None, None)

        assert state.shape == (StateEncoder.DISCARD_STATE_SIZE,)

    def test_encode_knock_state_shape(self):
        """Test knock state encoding produces correct shape."""
        encoder = StateEncoder()
        cards = [Card(Rank(r), Suit.CLUBS) for r in range(1, 11)]
        hand = Hand(cards)

        state = encoder.encode_knock_state(hand, None, None)

        assert state.shape == (StateEncoder.KNOCK_STATE_SIZE,)


class TestNetworks:
    """Tests for neural network models."""

    def test_draw_net_forward(self):
        """Test DrawNet forward pass."""
        net = DrawNet()
        batch_size = 4
        x = torch.randn(batch_size, StateEncoder.DRAW_STATE_SIZE)

        output = net(x)

        assert output.shape == (batch_size, 2)

    def test_discard_net_forward(self):
        """Test DiscardNet forward pass."""
        net = DiscardNet()
        batch_size = 4
        x = torch.randn(batch_size, StateEncoder.DISCARD_STATE_SIZE)

        output = net(x)

        # 52 outputs (one per card), not 11 (position-based)
        assert output.shape == (batch_size, 52)

    def test_knock_net_forward(self):
        """Test KnockNet forward pass."""
        net = KnockNet()
        batch_size = 4
        x = torch.randn(batch_size, StateEncoder.KNOCK_STATE_SIZE)

        output = net(x)

        assert output.shape == (batch_size, 2)

    def test_model_persistence(self, tmp_path):
        """Test saving and loading models."""
        draw_net = DrawNet()
        discard_net = DiscardNet()
        knock_net = KnockNet()
        metadata = {"episode": 100, "win_rate": 0.55}

        save_path = tmp_path / "model.pt"
        ModelPersistence.save(save_path, draw_net, discard_net, knock_net, metadata)

        assert save_path.exists()

        loaded_draw, loaded_discard, loaded_knock, loaded_meta = ModelPersistence.load(save_path)

        assert loaded_meta["episode"] == 100
        assert loaded_meta["win_rate"] == 0.55

        # Check networks are in eval mode
        assert not loaded_draw.training
        assert not loaded_discard.training
        assert not loaded_knock.training


class TestReplayBuffer:
    """Tests for experience replay buffer."""

    def test_add_and_sample(self):
        """Test adding and sampling experiences."""
        buffer = ReplayBuffer(capacity=100)

        # Add some experiences
        for i in range(10):
            exp = Experience(
                state=torch.randn(198),
                action=i % 2,
                reward=1.0,
                next_state=torch.randn(198),
                done=False,
                decision_type="draw",
            )
            buffer.add(exp)

        assert buffer.size("draw") == 10
        assert len(buffer) == 10

        # Sample a batch
        batch = buffer.sample(5, "draw")
        assert len(batch) == 5

    def test_separate_buffers(self):
        """Test that different decision types have separate buffers."""
        buffer = ReplayBuffer(capacity=100)

        # Add experiences to different types
        for decision_type in ["draw", "discard", "knock"]:
            exp = Experience(
                state=torch.randn(198),
                action=0,
                reward=1.0,
                next_state=torch.randn(198),
                done=False,
                decision_type=decision_type,
            )
            buffer.add(exp)

        assert buffer.size("draw") == 1
        assert buffer.size("discard") == 1
        assert buffer.size("knock") == 1
        assert len(buffer) == 3

    def test_batch_to_tensors(self):
        """Test converting batch to tensors."""
        batch = [
            Experience(
                state=torch.randn(198),
                action=1,
                reward=0.5,
                next_state=torch.randn(198),
                done=False,
                decision_type="draw",
            ),
            Experience(
                state=torch.randn(198),
                action=0,
                reward=-0.5,
                next_state=None,
                done=True,
                decision_type="draw",
            ),
        ]

        states, actions, rewards, next_states, dones = batch_to_tensors(batch, torch.device("cpu"))

        assert states.shape == (2, 198)
        assert actions.shape == (2,)
        assert rewards.shape == (2,)
        assert next_states.shape == (2, 198)
        assert dones.shape == (2,)
        assert dones[1].item() is True


class TestRewardCalculator:
    """Tests for reward calculation."""

    def test_default_config(self):
        """Test default reward configuration."""
        calc = RewardCalculator()

        assert calc.config.win_by_gin == 50.0
        assert calc.config.win_by_knock == 20.0

    def test_turn_reward_deadwood_reduction(self):
        """Test turn reward for deadwood reduction."""
        calc = RewardCalculator()

        reward = calc.turn_reward(
            deadwood_before=20,
            deadwood_after=15,
            melds_before=1,
            melds_after=1,
        )

        # 5 points reduction * 0.1 bonus = 0.5
        assert reward == pytest.approx(0.5)

    def test_turn_reward_meld_completion(self):
        """Test turn reward for completing a meld."""
        calc = RewardCalculator()

        reward = calc.turn_reward(
            deadwood_before=20,
            deadwood_after=20,
            melds_before=1,
            melds_after=2,
        )

        # 1 new meld * 1.0 bonus = 1.0
        assert reward == pytest.approx(1.0)

    def test_normalize_reward(self):
        """Test reward normalization."""
        calc = RewardCalculator()

        normalized = calc.normalize_reward(50.0, scale=100.0)

        assert normalized == pytest.approx(0.5)


class TestTrainerResume:
    """B5: --resume must load weights into the networks the optimizers own."""

    def _make_trainer(self, tmp_path):
        from gin_rummy.learning.trainer import Trainer, TrainingConfig

        config = TrainingConfig(num_episodes=5, min_buffer_size=10)
        return Trainer(config, tmp_path / "ckpt.pt")

    @staticmethod
    def _param_ids(optimizer):
        return {id(p) for group in optimizer.param_groups for p in group["params"]}

    def test_load_checkpoint_keeps_optimizers_bound_and_restores_state(self, tmp_path):
        source = self._make_trainer(tmp_path)
        source.current_exploration_rate = 0.42
        source._curriculum_idx = 1
        source._curriculum_episodes = 7
        with torch.no_grad():
            for p in source.learning_ai.draw_net.parameters():
                p.add_(1.0)
        source._save_checkpoint(123)

        target = self._make_trainer(tmp_path)
        draw_net_before = target.learning_ai.draw_net
        episode = target.load_checkpoint(tmp_path / "ckpt.pt")

        # Same network objects -> optimizers still train the loaded weights.
        assert target.learning_ai.draw_net is draw_net_before
        assert self._param_ids(target.draw_optimizer) == {id(p) for p in target.learning_ai.draw_net.parameters()}
        assert self._param_ids(target.discard_optimizer) == {id(p) for p in target.learning_ai.discard_net.parameters()}
        assert self._param_ids(target.knock_optimizer) == {id(p) for p in target.learning_ai.knock_net.parameters()}

        # Weights actually loaded.
        for a, b in zip(
            source.learning_ai.draw_net.parameters(), target.learning_ai.draw_net.parameters(), strict=True
        ):
            assert torch.equal(a, b)
        for a, b in zip(target.learning_ai.draw_net.parameters(), target.target_ai.draw_net.parameters(), strict=True):
            assert torch.equal(a, b)

        # Training state restored.
        assert episode == 123
        assert target._start_episode == 123
        assert target.current_exploration_rate == pytest.approx(0.42)
        assert target.learning_ai.exploration_rate == pytest.approx(0.42)
        assert target._curriculum_idx == 1
        assert target._curriculum_episodes == 7

    def test_execute_ai_turn_forwards_opponent_actions_to_learning_ai(self):
        """B4 end to end: LearningAI's opponent model fills up via the shared runner."""
        from gin_rummy.ai import BasicAI
        from gin_rummy.game import Game
        from gin_rummy.game_runner import execute_ai_turn
        from gin_rummy.learning.learning_ai import LearningAI

        learner = LearningAI()
        opponent = BasicAI()
        game = Game("Learner", "Basic")
        game.dealer_idx = 1  # dealer takes the first turn, so the opponent acts first
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        assert game.current_player_idx == 1

        execute_ai_turn(game, opponent, other_ai=learner)
        assert learner.opponent_model.total_discards == 1


class TestLearningFactory:
    def test_make_ai_learning(self):
        from gin_rummy.ai import make_ai
        from gin_rummy.learning.learning_ai import LearningAI

        ai = make_ai("learning", exploration_rate=0.0)
        assert type(ai) is LearningAI
        assert LearningAI.needs_context is True


class TestLearningReasoning:
    """B8: LearningAI's *_with_reasoning twins describe its own decision, not BasicAI's."""

    def _pair(self):
        import copy

        from gin_rummy.learning.learning_ai import LearningAI

        ai = LearningAI(exploration_rate=0.0)
        return ai, copy.deepcopy(ai)  # identical random weights

    def test_twins_agree_and_mention_q_values(self):
        from gin_rummy.game import Game
        from gin_rummy.models import Hand

        for seed in range(20):
            random.seed(seed)
            game = Game("A", "B")
            game.deal()
            game.discard_to_start(game.current_player.hand[0])
            idx = game.current_player_idx
            ctx = game.get_game_context(idx)
            hand = game.players[idx].hand
            top = game.top_of_discard
            eleven = Hand(list(hand) + [game.deck._cards[0]])

            a, b = self._pair()
            assert a.decide_draw(hand, top, ctx) == b.decide_draw_with_reasoning(hand, top, ctx).choice
            a, b = self._pair()
            a._drawn_card = b._drawn_card = eleven[-1]
            assert a.decide_discard(eleven, ctx) == b.decide_discard_with_reasoning(eleven, ctx).card
            a, b = self._pair()
            assert a.should_knock(hand, ctx) == b.should_knock_with_reasoning(hand, ctx).should_knock

        r = b.decide_draw_with_reasoning(hand, top, ctx)
        assert "Q" in r.reasoning or "DrawNet" in r.reasoning

    def test_context_threshold_blocks_knock(self):
        from dataclasses import replace

        from tests.helpers import hand, make_context

        h = hand("AS 2S 3S 4H 5H 6H 7C 8C 9C 7D")
        ai, _ = self._pair()
        oklahoma = replace(make_context(h), knock_threshold=5)
        assert ai.should_knock(h, oklahoma) is False
        assert ai.should_knock_with_reasoning(h, oklahoma).should_knock is False
