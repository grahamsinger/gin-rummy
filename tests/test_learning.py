"""Tests for the learning module.

Note: These tests require the optional 'learning' dependencies.
Run with: uv sync --extra learning && uv run pytest tests/test_learning.py
"""

import pytest

# Skip all tests if torch is not available
torch = pytest.importorskip("torch")
numpy = pytest.importorskip("numpy")

from gin_rummy.models import Card, Rank, Suit, Hand
from gin_rummy.learning.state import StateEncoder, card_to_index, NUM_CARDS
from gin_rummy.learning.models import DrawNet, DiscardNet, KnockNet, ModelPersistence
from gin_rummy.learning.replay import Experience, ReplayBuffer, batch_to_tensors
from gin_rummy.learning.rewards import RewardCalculator, RewardConfig


class TestStateEncoder:
    """Tests for state encoding."""

    def test_card_to_index(self):
        """Test card to index conversion."""
        # Ace of Clubs should be 0
        ace_clubs = Card(Rank.ACE, Suit.CLUBS)
        assert card_to_index(ace_clubs) == 0

        # King of Spades should be 51
        king_spades = Card(Rank.KING, Suit.SPADES)
        assert card_to_index(king_spades) == 51

        # Ace of Diamonds should be 13
        ace_diamonds = Card(Rank.ACE, Suit.DIAMONDS)
        assert card_to_index(ace_diamonds) == 13

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
        assert encoding[card_to_index(cards[0])] == 1.0
        assert encoding[card_to_index(cards[1])] == 1.0
        assert encoding[card_to_index(cards[2])] == 1.0

    def test_encode_card(self):
        """Test single card encoding."""
        encoder = StateEncoder()
        card = Card(Rank.FIVE, Suit.DIAMONDS)

        encoding = encoder.encode_card(card)

        assert encoding.shape == (NUM_CARDS,)
        assert encoding.sum() == 1
        assert encoding[card_to_index(card)] == 1.0

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

        loaded_draw, loaded_discard, loaded_knock, loaded_meta = ModelPersistence.load(
            save_path
        )

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

        states, actions, rewards, next_states, dones = batch_to_tensors(
            batch, torch.device("cpu")
        )

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
