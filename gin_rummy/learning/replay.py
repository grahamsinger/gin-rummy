"""Experience replay buffer for DQN training.

Stores transitions (state, action, reward, next_state, done) and provides
random sampling for stable training.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Literal

import torch


DecisionType = Literal["draw", "discard", "knock"]


@dataclass
class Experience:
    """A single experience tuple for replay.

    Attributes:
        state: State tensor at time t
        action: Action taken (integer index)
        reward: Reward received
        next_state: State tensor at time t+1 (or None if terminal)
        done: Whether this was a terminal transition
        decision_type: Which decision network this experience is for
    """

    state: torch.Tensor
    action: int
    reward: float
    next_state: torch.Tensor | None
    done: bool
    decision_type: DecisionType


class ReplayBuffer:
    """Experience replay buffer with separate storage by decision type.

    Stores experiences in a circular buffer and provides random sampling.
    Experiences are stored separately for each decision type to allow
    balanced training of all three networks.
    """

    def __init__(self, capacity: int = 100_000) -> None:
        """Initialize replay buffer.

        Args:
            capacity: Maximum number of experiences per decision type.
        """
        self.capacity = capacity
        self._buffers: dict[DecisionType, deque[Experience]] = {
            "draw": deque(maxlen=capacity),
            "discard": deque(maxlen=capacity),
            "knock": deque(maxlen=capacity),
        }

    def add(self, experience: Experience) -> None:
        """Add an experience to the buffer.

        Args:
            experience: Experience tuple to add.
        """
        self._buffers[experience.decision_type].append(experience)

    def sample(
        self,
        batch_size: int,
        decision_type: DecisionType | None = None,
    ) -> list[Experience]:
        """Sample a random batch of experiences.

        Args:
            batch_size: Number of experiences to sample.
            decision_type: If specified, sample only from this type.
                          If None, sample from all types combined.

        Returns:
            List of sampled experiences.
        """
        if decision_type is not None:
            buffer = self._buffers[decision_type]
            if len(buffer) < batch_size:
                return list(buffer)
            return random.sample(list(buffer), batch_size)
        else:
            # Combine all buffers
            all_experiences = []
            for buffer in self._buffers.values():
                all_experiences.extend(buffer)
            if len(all_experiences) < batch_size:
                return all_experiences
            return random.sample(all_experiences, batch_size)

    def size(self, decision_type: DecisionType | None = None) -> int:
        """Get the number of experiences in the buffer.

        Args:
            decision_type: If specified, count only this type.

        Returns:
            Number of experiences.
        """
        if decision_type is not None:
            return len(self._buffers[decision_type])
        return sum(len(buf) for buf in self._buffers.values())

    def __len__(self) -> int:
        """Total number of experiences across all types."""
        return self.size()

    def clear(self) -> None:
        """Clear all experiences from the buffer."""
        for buffer in self._buffers.values():
            buffer.clear()


def batch_to_tensors(
    batch: list[Experience],
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Convert a batch of experiences to tensors for training.

    Args:
        batch: List of Experience objects.
        device: Device to put tensors on.

    Returns:
        Tuple of (states, actions, rewards, next_states, dones).
        next_states will have zeros for terminal states.
    """
    states = torch.stack([exp.state for exp in batch]).to(device)
    actions = torch.tensor([exp.action for exp in batch], dtype=torch.long, device=device)
    rewards = torch.tensor([exp.reward for exp in batch], dtype=torch.float32, device=device)

    # Handle terminal states (next_state is None)
    non_terminal_mask = torch.tensor(
        [exp.next_state is not None for exp in batch],
        dtype=torch.bool,
        device=device,
    )

    # Create next_states tensor with zeros for terminal states
    state_size = states.shape[1]
    next_states = torch.zeros(len(batch), state_size, device=device)
    for i, exp in enumerate(batch):
        if exp.next_state is not None:
            next_states[i] = exp.next_state

    dones = torch.tensor([exp.done for exp in batch], dtype=torch.bool, device=device)

    return states, actions, rewards, next_states, dones
