"""Training infrastructure for LearningAI.

Provides the main training loop with experience collection, batch training,
curriculum learning, and evaluation.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from gin_rummy.ai import BasicAI, DrawChoice, make_ai
from gin_rummy.game import Game
from gin_rummy.game_runner import TurnResult, execute_ai_turn
from gin_rummy.learning.learning_ai import LearningAI
from gin_rummy.learning.models import ModelPersistence
from gin_rummy.learning.replay import (
    Experience,
    ReplayBuffer,
    batch_to_tensors,
)
from gin_rummy.learning.rewards import RewardCalculator, RewardConfig
from gin_rummy.learning.state import StateEncoder

if TYPE_CHECKING:
    from torch.utils.tensorboard import SummaryWriter


logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for training."""

    # Training duration
    num_episodes: int = 10_000
    max_rounds_per_game: int = 50
    target_score: int = 100

    # Network training
    batch_size: int = 64
    learning_rate: float = 0.001
    gamma: float = 0.99  # Discount factor

    # Exploration schedule
    exploration_start: float = 1.0
    exploration_end: float = 0.05
    exploration_decay: float = 0.9995

    # Target network
    target_update_freq: int = 100  # Episodes between target network updates

    # Replay buffer
    buffer_capacity: int = 100_000
    min_buffer_size: int = 1000  # Start training after this many experiences

    # Checkpointing
    save_freq: int = 1000  # Save every N episodes
    eval_freq: int = 500  # Evaluate every N episodes
    eval_games: int = 100  # Games per evaluation

    # Curriculum learning
    curriculum: list[tuple[str, int]] = field(
        default_factory=lambda: [
            ("basic", 5000),
            ("context", 5000),
            ("self", 10000),
        ]
    )

    # Reward configuration
    reward_config: RewardConfig = field(default_factory=RewardConfig)

    # Reproducibility: seeds random, numpy and torch before the networks are
    # built (None = unseeded)
    seed: int | None = None


def seed_everything(seed: int) -> None:
    """Seed every generator the trainer draws from (deck, exploration, replay sampling, weights)."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


@dataclass
class TrainingMetrics:
    """Metrics tracked during training."""

    episode: int = 0
    total_reward: float = 0.0
    win_rate: float = 0.0
    avg_points_per_game: float = 0.0
    exploration_rate: float = 1.0

    # Loss values
    draw_loss: float = 0.0
    discard_loss: float = 0.0
    knock_loss: float = 0.0

    # Buffer sizes
    buffer_size: int = 0


class Trainer:
    """Main trainer for LearningAI.

    Orchestrates the training loop:
    1. Play games collecting experiences
    2. Store experiences in replay buffer
    3. Sample batches and train networks
    4. Update exploration rate
    5. Periodically evaluate and save checkpoints
    """

    def __init__(
        self,
        config: TrainingConfig,
        save_path: Path,
        tensorboard_path: Path | None = None,
    ) -> None:
        """Initialize trainer.

        Args:
            config: Training configuration.
            save_path: Path to save model checkpoints.
            tensorboard_path: Path for TensorBoard logs (optional).
        """
        self.config = config
        self.save_path = save_path
        self.tensorboard_path = tensorboard_path

        if config.seed is not None:
            seed_everything(config.seed)

        # Initialize device (CUDA > CPU, MPS has dtype issues)
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")
        logger.info("Using device: %s", self.device)

        # Initialize learning AI (will be trained)
        self.learning_ai = LearningAI(
            exploration_rate=config.exploration_start,
            device=self.device,
        )
        self.learning_ai.train_mode()

        # Target networks for stable training
        self.target_ai = LearningAI(device=self.device)
        self._sync_target_networks()
        self.target_ai.eval_mode()

        # Optimizers for each network
        self.draw_optimizer = optim.Adam(
            self.learning_ai.draw_net.parameters(),
            lr=config.learning_rate,
        )
        self.discard_optimizer = optim.Adam(
            self.learning_ai.discard_net.parameters(),
            lr=config.learning_rate,
        )
        self.knock_optimizer = optim.Adam(
            self.learning_ai.knock_net.parameters(),
            lr=config.learning_rate,
        )

        # Replay buffer
        self.replay_buffer = ReplayBuffer(capacity=config.buffer_capacity)

        # Reward calculator
        self.reward_calculator = RewardCalculator(config.reward_config)

        # State encoder
        self.encoder = StateEncoder()

        # Metrics tracking
        self.metrics_history: list[TrainingMetrics] = []
        self.current_exploration_rate = config.exploration_start

        # Curriculum tracking
        self._curriculum_idx = 0
        self._curriculum_episodes = 0

        # Episode to start from (non-zero after load_checkpoint)
        self._start_episode = 0

        # TensorBoard writer
        self._writer: SummaryWriter | None = None
        if tensorboard_path:
            try:
                from torch.utils.tensorboard import SummaryWriter

                self._writer = SummaryWriter(str(tensorboard_path))
            except ImportError:
                logger.warning("TensorBoard not available")

    def load_checkpoint(self, path: Path) -> int:
        """Resume training state from a checkpoint saved by _save_checkpoint.

        Weights are loaded *into* the existing networks so that the
        optimizers (which hold references to those parameters) keep
        training the right tensors. Exploration rate and curriculum
        position are restored from the checkpoint metadata.

        Args:
            path: Checkpoint file path.

        Returns:
            The episode number the checkpoint was saved at.
        """
        draw_net, discard_net, knock_net, metadata = ModelPersistence.load(path, self.device)
        self.learning_ai.draw_net.load_state_dict(draw_net.state_dict())
        self.learning_ai.discard_net.load_state_dict(discard_net.state_dict())
        self.learning_ai.knock_net.load_state_dict(knock_net.state_dict())
        self.learning_ai.metadata = metadata
        self.learning_ai.train_mode()
        self._sync_target_networks()

        self.current_exploration_rate = float(metadata.get("exploration_rate", self.config.exploration_start))
        self.learning_ai.exploration_rate = self.current_exploration_rate
        self._curriculum_idx = int(metadata.get("curriculum_idx", 0))
        self._curriculum_episodes = int(metadata.get("curriculum_episodes", 0))
        self._start_episode = int(metadata.get("episode", 0))

        logger.info(
            "Loaded checkpoint %s (episode %d, exploration=%.3f, curriculum stage %d)",
            path,
            self._start_episode,
            self.current_exploration_rate,
            self._curriculum_idx,
        )
        return self._start_episode

    def _sync_target_networks(self) -> None:
        """Copy weights from learning networks to target networks."""
        self.target_ai.draw_net.load_state_dict(self.learning_ai.draw_net.state_dict())
        self.target_ai.discard_net.load_state_dict(self.learning_ai.discard_net.state_dict())
        self.target_ai.knock_net.load_state_dict(self.learning_ai.knock_net.state_dict())

    def _get_opponent(self) -> BasicAI:
        """Get opponent based on curriculum stage."""
        if self._curriculum_idx >= len(self.config.curriculum):
            # Past curriculum, use self-play
            return LearningAI(
                model_path=self.save_path if self.save_path.exists() else None,
                exploration_rate=0.0,
                device=self.device,
            )

        opponent_type, _ = self.config.curriculum[self._curriculum_idx]

        if opponent_type == "self":
            # Self-play with frozen copy
            return LearningAI(
                model_path=self.save_path if self.save_path.exists() else None,
                exploration_rate=0.0,
                device=self.device,
            )
        try:
            return make_ai(opponent_type)
        except ValueError:
            logger.warning("Unknown opponent type: %s, using BasicAI", opponent_type)
            return BasicAI()

    def _update_curriculum(self) -> None:
        """Update curriculum progress."""
        if self._curriculum_idx >= len(self.config.curriculum):
            return

        _, episodes_for_stage = self.config.curriculum[self._curriculum_idx]
        self._curriculum_episodes += 1

        if self._curriculum_episodes >= episodes_for_stage:
            self._curriculum_idx += 1
            self._curriculum_episodes = 0
            if self._curriculum_idx < len(self.config.curriculum):
                new_stage = self.config.curriculum[self._curriculum_idx][0]
                logger.info("\nCurriculum advancing to stage: %s", new_stage)

    def train(self, callback: Callable[[TrainingMetrics], None] | None = None) -> None:
        """Run the full training loop.

        Args:
            callback: Optional callback called after each episode with metrics.
        """
        if self._start_episode >= self.config.num_episodes:
            logger.warning(
                "Checkpoint already has %d completed episodes and num_episodes is %d; "
                "nothing to train. --episodes is the total, not additional episodes.",
                self._start_episode,
                self.config.num_episodes,
            )
        else:
            logger.info(
                "Starting training: episodes %d to %d",
                self._start_episode,
                self.config.num_episodes,
            )

        for episode in range(self._start_episode, self.config.num_episodes):
            # Train one episode
            episode_reward = self._train_episode()

            # Update exploration rate
            self._update_exploration_rate()

            # Update curriculum
            self._update_curriculum()

            # Update target network periodically
            if episode % self.config.target_update_freq == 0:
                self._sync_target_networks()

            # Create metrics
            metrics = TrainingMetrics(
                episode=episode,
                total_reward=episode_reward,
                exploration_rate=self.current_exploration_rate,
                buffer_size=len(self.replay_buffer),
            )

            # Evaluate periodically
            if episode > 0 and episode % self.config.eval_freq == 0:
                win_rate, avg_points = self._evaluate()
                metrics.win_rate = win_rate
                metrics.avg_points_per_game = avg_points
                logger.info(
                    "\nEpisode %d: win_rate=%.2f, avg_points=%.1f, exploration=%.3f",
                    episode,
                    win_rate,
                    avg_points,
                    self.current_exploration_rate,
                )

            # Save checkpoint periodically. The stored episode is the number
            # of *completed* episodes, so a resume starts on the next one.
            if episode > 0 and episode % self.config.save_freq == 0:
                self._save_checkpoint(episode + 1)

            # Log to TensorBoard
            if self._writer:
                self._writer.add_scalar("reward/episode", episode_reward, episode)
                self._writer.add_scalar("exploration_rate", self.current_exploration_rate, episode)
                if metrics.win_rate > 0:
                    self._writer.add_scalar("eval/win_rate", metrics.win_rate, episode)

            self.metrics_history.append(metrics)

            # Callback
            if callback:
                callback(metrics)

        # Final save
        self._save_checkpoint(self.config.num_episodes)

        if self._writer:
            self._writer.close()

        logger.info("Training complete!")

    def _train_episode(self) -> float:
        """Run one training episode (one game).

        Returns:
            Total reward for the episode.
        """
        opponent = self._get_opponent()
        total_reward = 0.0

        # Play a full game
        game = Game("LearningAI", "Opponent")
        game.deal()

        rounds_played = 0
        while (
            max(p.score for p in game.players) < self.config.target_score
            and rounds_played < self.config.max_rounds_per_game
        ):
            # Play one round collecting experiences
            round_reward = self._play_round(game, opponent)
            total_reward += round_reward
            rounds_played += 1

            # Start new round if game continues
            if max(p.score for p in game.players) < self.config.target_score:
                game.new_round()
                game.deal()

                # Reset AI tracking for new hand
                self.learning_ai.reset_for_new_hand()
                opponent.reset_for_new_hand()

        # Train on collected experiences
        if len(self.replay_buffer) >= self.config.min_buffer_size:
            self._train_batch()

        return total_reward

    def _play_round(self, game: Game, opponent: BasicAI) -> float:
        """Play one round collecting experiences.

        Args:
            game: Game instance.
            opponent: Opponent AI.

        Returns:
            Reward for the round.
        """
        round_reward = 0.0
        learning_player_idx = 0  # LearningAI is player 0

        # Store experiences for this round
        round_experiences: list[Experience] = []

        # Handle first discard (non-dealer discards to start the discard pile)
        non_dealer_idx = 1 - game.dealer_idx
        first_discard_ai = self.learning_ai if non_dealer_idx == 0 else opponent
        discard = first_discard_ai.decide_discard(game.players[non_dealer_idx].hand)
        game.discard_to_start(discard)

        # Record first discard for opponent tracking
        if non_dealer_idx == 0:
            # Learning AI discarded, record for opponent
            opponent.record_opponent_discard(discard)
        else:
            # Opponent discarded, record for learning AI
            self.learning_ai.record_opponent_discard(discard)

        while game.phase.name not in ("ROUND_OVER", "KNOCKED"):
            current_player_idx = game.current_player_idx
            current_player = game.players[current_player_idx]

            # Get the AI for current player
            ai = self.learning_ai if current_player_idx == learning_player_idx else opponent

            ai.update_context(game.get_game_context(current_player_idx))

            # Store state before turn (for learning AI only)
            state_before = None
            deadwood_before = 0
            melds_before = 0
            if current_player_idx == learning_player_idx:
                hand = current_player.hand
                ctx = game.get_game_context(current_player_idx)
                state_before = self.encoder.encode_draw_state(
                    hand, game.top_of_discard, ctx, self.learning_ai.opponent_model
                )
                deadwood_before = hand.deadwood_total
                melds_before = len(hand.analyze().melds)

            # Execute turn
            other_ai = opponent if current_player_idx == learning_player_idx else self.learning_ai
            result, actions, round_result = execute_ai_turn(game, ai, other_ai)

            # Collect experiences for learning AI
            if current_player_idx == learning_player_idx and actions and state_before is not None:
                hand = current_player.hand
                deadwood_after = hand.deadwood_total
                melds_after = len(hand.analyze().melds)

                # Calculate turn reward
                turn_reward = self.reward_calculator.turn_reward(
                    deadwood_before, deadwood_after, melds_before, melds_after
                )

                # Create experiences for each decision
                ctx = game.get_game_context(current_player_idx)

                # Draw experience
                # next_state is None because we transition to discard (different state size)
                drew_from_discard = actions.draw_source == DrawChoice.DISCARD
                draw_action = 0 if actions.draw_source == DrawChoice.DECK else 1

                # Calculate draw-specific reward (penalize wasteful discard draws)
                draw_specific_reward = self.reward_calculator.draw_reward(
                    drew_from_discard=drew_from_discard,
                    drawn_card=actions.drawn_card,
                    discarded_card=actions.discarded_card,
                    deadwood_before=deadwood_before,
                    deadwood_after=deadwood_after,
                )
                draw_reward = (turn_reward / 3) + draw_specific_reward

                round_experiences.append(
                    Experience(
                        state=state_before,
                        action=draw_action,
                        reward=draw_reward,
                        next_state=None,  # Different state space (discard), so treat as terminal
                        done=False,
                        decision_type="draw",
                    )
                )

                # Discard experience (requires both drawn_card and discarded_card)
                if actions.discarded_card and actions.drawn_card:
                    # Use card index (0-51) instead of position in hand
                    discard_action = actions.discarded_card.index

                    discard_state = self.encoder.encode_discard_state(
                        hand, actions.drawn_card, ctx, self.learning_ai.opponent_model
                    )
                    knock_state = self.encoder.encode_knock_state(hand, ctx, self.learning_ai.opponent_model)

                    round_experiences.append(
                        Experience(
                            state=discard_state,
                            action=discard_action,
                            reward=turn_reward / 3,
                            next_state=None,  # Different state space (knock), so treat as terminal
                            done=False,
                            decision_type="discard",
                        )
                    )

                    # Knock experience (if could have knocked)
                    if hand.deadwood_total <= 10:
                        knock_action = 1 if actions.did_knock else 0
                        round_experiences.append(
                            Experience(
                                state=knock_state,
                                action=knock_action,
                                reward=turn_reward / 3,
                                next_state=None,  # Will be updated at round end
                                done=actions.did_knock,
                                decision_type="knock",
                            )
                        )

            # Check for round end
            if result == TurnResult.DRAW:
                # Round ended in draw
                break
            elif result == TurnResult.KNOCKED and round_result:
                # Round ended, calculate final rewards
                final_reward = self.reward_calculator.round_end_reward(round_result, "LearningAI")
                round_reward += final_reward

                # Update last experiences with terminal reward
                for exp in round_experiences[-3:]:  # Last 3 decisions
                    exp.reward += final_reward / 3
                    exp.done = True

                break

        # Add all experiences to buffer
        for exp in round_experiences:
            self.replay_buffer.add(exp)

        return round_reward

    def _train_batch(self) -> None:
        """Train networks on a batch from replay buffer."""
        # Train each network on its respective experiences
        for decision_type, network, optimizer, target_network in [
            ("draw", self.learning_ai.draw_net, self.draw_optimizer, self.target_ai.draw_net),
            ("discard", self.learning_ai.discard_net, self.discard_optimizer, self.target_ai.discard_net),
            ("knock", self.learning_ai.knock_net, self.knock_optimizer, self.target_ai.knock_net),
        ]:
            batch = self.replay_buffer.sample(self.config.batch_size, decision_type)
            if len(batch) < self.config.batch_size // 2:
                continue

            # Convert to tensors
            states, actions, rewards, next_states, dones = batch_to_tensors(batch, self.device)

            # Compute current Q values
            network.train()
            current_q = network(states)
            current_q_values = current_q.gather(1, actions.unsqueeze(1)).squeeze()

            # Compute target Q values
            with torch.no_grad():
                next_q = target_network(next_states)
                max_next_q = next_q.max(dim=1)[0]
                target_q_values = rewards + (self.config.gamma * max_next_q * (~dones).float())

            # Compute loss and update
            loss = nn.functional.mse_loss(current_q_values, target_q_values)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    def _update_exploration_rate(self) -> None:
        """Decay exploration rate."""
        self.current_exploration_rate = max(
            self.config.exploration_end,
            self.current_exploration_rate * self.config.exploration_decay,
        )
        self.learning_ai.set_exploration_rate(self.current_exploration_rate)

    def _evaluate(self) -> tuple[float, float]:
        """Evaluate current policy against BasicAI.

        Returns:
            Tuple of (win_rate, average_points_per_game).
        """
        self.learning_ai.eval_mode()
        old_exploration = self.learning_ai.exploration_rate
        self.learning_ai.set_exploration_rate(0.0)

        wins = 0
        total_points = 0
        opponent = BasicAI()

        for _ in range(self.config.eval_games):
            game = Game("LearningAI", "Opponent")
            game.deal()

            rounds = 0
            while (
                max(p.score for p in game.players) < self.config.target_score
                and rounds < self.config.max_rounds_per_game
            ):
                self._play_eval_round(game, opponent)
                rounds += 1
                if max(p.score for p in game.players) < self.config.target_score:
                    game.new_round()
                    game.deal()
                    self.learning_ai.reset_for_new_hand()

            # Check winner
            if game.players[0].score >= self.config.target_score:
                wins += 1
            total_points += game.players[0].score

        # Restore training mode
        self.learning_ai.set_exploration_rate(old_exploration)
        self.learning_ai.train_mode()

        win_rate = wins / self.config.eval_games
        avg_points = total_points / self.config.eval_games

        return win_rate, avg_points

    def _play_eval_round(self, game: Game, opponent: BasicAI) -> None:
        """Play one evaluation round (no experience collection)."""
        # Handle first discard (non-dealer discards to start the discard pile)
        non_dealer_idx = 1 - game.dealer_idx
        first_discard_ai = self.learning_ai if non_dealer_idx == 0 else opponent
        discard = first_discard_ai.decide_discard(game.players[non_dealer_idx].hand)
        game.discard_to_start(discard)

        while game.phase.name not in ("ROUND_OVER", "KNOCKED"):
            current_player_idx = game.current_player_idx
            ai = self.learning_ai if current_player_idx == 0 else opponent

            ai.update_context(game.get_game_context(current_player_idx))

            other_ai = opponent if current_player_idx == 0 else self.learning_ai
            result, _, _ = execute_ai_turn(game, ai, other_ai)

            if result in (TurnResult.DRAW, TurnResult.KNOCKED):
                break

    def _save_checkpoint(self, episode: int) -> None:
        """Save model checkpoint.

        Args:
            episode: Current episode number.
        """
        self.save_path.parent.mkdir(parents=True, exist_ok=True)

        metadata = {
            "episode": episode,
            "exploration_rate": self.current_exploration_rate,
            "curriculum_idx": self._curriculum_idx,
            "curriculum_episodes": self._curriculum_episodes,
        }

        ModelPersistence.save(
            self.save_path,
            self.learning_ai.draw_net,
            self.learning_ai.discard_net,
            self.learning_ai.knock_net,
            metadata,
        )

        logger.info("Saved checkpoint at episode %d to %s", episode, self.save_path)


def main() -> None:
    """CLI entry point for training."""
    import argparse

    parser = argparse.ArgumentParser(description="Train LearningAI for Gin Rummy")
    parser.add_argument(
        "--episodes",
        type=int,
        default=10000,
        help="Total number of training episodes (when resuming, this includes episodes already completed)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/learning_ai.pt",
        help="Path to save trained model",
    )
    parser.add_argument(
        "--tensorboard",
        type=str,
        default="runs/gin_learning",
        help="TensorBoard log directory",
    )
    parser.add_argument(
        "--resume",
        type=str,
        help="Resume training from checkpoint",
    )
    parser.add_argument(
        "--eval-freq",
        type=int,
        default=500,
        help="Evaluate every N episodes",
    )
    parser.add_argument(
        "--save-freq",
        type=int,
        default=1000,
        help="Save checkpoint every N episodes",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed random, numpy and torch for a reproducible run",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging - suppress game logs unless verbose
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    else:
        # Only show trainer logs, suppress noisy game/AI logs
        logging.basicConfig(
            level=logging.WARNING,
            format="%(message)s",
        )
        # But keep trainer logger at INFO for important messages
        logging.getLogger("gin_rummy.learning.trainer").setLevel(logging.INFO)

    # Create config
    config = TrainingConfig(
        num_episodes=args.episodes,
        eval_freq=args.eval_freq,
        save_freq=args.save_freq,
        seed=args.seed,
    )

    # Create trainer
    save_path = Path(args.output)
    tensorboard_path = Path(args.tensorboard) if args.tensorboard else None

    trainer = Trainer(config, save_path, tensorboard_path)

    # Resume from checkpoint if specified
    if args.resume:
        resume_path = Path(args.resume)
        if resume_path.exists():
            logger.info("Resuming from checkpoint: %s", resume_path)
            trainer.load_checkpoint(resume_path)
        else:
            logger.warning("Checkpoint %s not found; starting from scratch", resume_path)

    # Progress bar state
    import sys
    import time

    start_time = time.time()
    last_rewards: list[float] = []

    def format_time(seconds: float) -> str:
        """Format seconds as HH:MM:SS or MM:SS."""
        if seconds < 3600:
            return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"
        return f"{int(seconds // 3600)}:{int((seconds % 3600) // 60):02d}:{int(seconds % 60):02d}"

    def progress_callback(metrics: TrainingMetrics) -> None:
        nonlocal last_rewards

        # Track recent rewards for averaging
        last_rewards.append(metrics.total_reward)
        if len(last_rewards) > 100:
            last_rewards = last_rewards[-100:]

        # Update progress bar every episode
        elapsed = time.time() - start_time
        progress = metrics.episode / config.num_episodes

        eta = elapsed / progress - elapsed if progress > 0 else 0

        avg_reward = sum(last_rewards) / len(last_rewards)

        # Build progress bar
        bar_width = 30
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)

        # Print progress line (overwrite previous)
        status = (
            f"\r[{bar}] {metrics.episode:>6}/{config.num_episodes} "
            f"| ε={metrics.exploration_rate:.3f} "
            f"| avg_r={avg_reward:>6.1f} "
            f"| buf={metrics.buffer_size:>6} "
            f"| {format_time(elapsed)}<{format_time(eta)}"
        )
        sys.stdout.write(status)
        sys.stdout.flush()

    # Run training
    print(f"Training {config.num_episodes} episodes on {trainer.device}...")
    trainer.train(callback=progress_callback)

    print(f"\n\nTraining complete! Model saved to {save_path}")


if __name__ == "__main__":
    main()
