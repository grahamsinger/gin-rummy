"""Neural network models for Deep Q-Learning.

Three specialized networks for the three decision types:
- DrawNet: Deck vs discard decision
- DiscardNet: Which card to discard
- KnockNet: Whether to knock
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

from gin_rummy.learning.state import StateEncoder


class DrawNet(nn.Module):
    """Network for draw decisions (deck vs discard).

    Input: State vector (DRAW_STATE_SIZE features)
    Output: 2 Q-values [Q(deck), Q(discard)]
    """

    def __init__(
        self,
        state_size: int = StateEncoder.DRAW_STATE_SIZE,
        hidden_sizes: list[int] | None = None,
    ):
        super().__init__()

        if hidden_sizes is None:
            hidden_sizes = [128, 64]

        layers: list[nn.Module] = []
        prev_size = state_size

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, hidden_size))
            layers.append(nn.ReLU())
            prev_size = hidden_size

        layers.append(nn.Linear(prev_size, 2))

        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass returning Q-values for [deck, discard]."""
        return self.network(x)


class DiscardNet(nn.Module):
    """Network for discard decisions.

    Input: State vector (DISCARD_STATE_SIZE features)
    Output: 11 Q-values, one for each card position in hand

    During inference, only the first N outputs are used (where N = hand size).
    Invalid positions are masked.
    """

    def __init__(
        self,
        state_size: int = StateEncoder.DISCARD_STATE_SIZE,
        hidden_sizes: list[int] | None = None,
    ):
        super().__init__()

        if hidden_sizes is None:
            hidden_sizes = [256, 128]

        layers: list[nn.Module] = []
        prev_size = state_size

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, hidden_size))
            layers.append(nn.ReLU())
            prev_size = hidden_size

        # Output 11 Q-values (max hand size after drawing)
        layers.append(nn.Linear(prev_size, 11))

        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass returning Q-values for each card position."""
        return self.network(x)


class KnockNet(nn.Module):
    """Network for knock decisions.

    Input: State vector (KNOCK_STATE_SIZE features)
    Output: 2 Q-values [Q(don't knock), Q(knock)]
    """

    def __init__(
        self,
        state_size: int = StateEncoder.KNOCK_STATE_SIZE,
        hidden_sizes: list[int] | None = None,
    ):
        super().__init__()

        if hidden_sizes is None:
            hidden_sizes = [64, 32]

        layers: list[nn.Module] = []
        prev_size = state_size

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, hidden_size))
            layers.append(nn.ReLU())
            prev_size = hidden_size

        layers.append(nn.Linear(prev_size, 2))

        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass returning Q-values for [don't knock, knock]."""
        return self.network(x)


class ModelPersistence:
    """Save and load trained models with metadata."""

    @staticmethod
    def save(
        path: Path,
        draw_net: DrawNet,
        discard_net: DiscardNet,
        knock_net: KnockNet,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save all networks and metadata to a checkpoint file.

        Args:
            path: Path to save the checkpoint
            draw_net: Trained DrawNet
            discard_net: Trained DiscardNet
            knock_net: Trained KnockNet
            metadata: Optional training metadata (episode, metrics, config)
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            "draw_net_state": draw_net.state_dict(),
            "discard_net_state": discard_net.state_dict(),
            "knock_net_state": knock_net.state_dict(),
            "metadata": metadata or {},
        }

        torch.save(checkpoint, path)

    @staticmethod
    def load(
        path: Path,
        device: torch.device | None = None,
    ) -> tuple[DrawNet, DiscardNet, KnockNet, dict[str, Any]]:
        """Load networks and metadata from a checkpoint file.

        Args:
            path: Path to the checkpoint file
            device: Device to load tensors to (default: CPU)

        Returns:
            Tuple of (draw_net, discard_net, knock_net, metadata)
        """
        if device is None:
            device = torch.device("cpu")

        checkpoint = torch.load(path, map_location=device, weights_only=True)

        draw_net = DrawNet()
        discard_net = DiscardNet()
        knock_net = KnockNet()

        draw_net.load_state_dict(checkpoint["draw_net_state"])
        discard_net.load_state_dict(checkpoint["discard_net_state"])
        knock_net.load_state_dict(checkpoint["knock_net_state"])

        # Set to evaluation mode
        draw_net.eval()
        discard_net.eval()
        knock_net.eval()

        return draw_net, discard_net, knock_net, checkpoint.get("metadata", {})

    @staticmethod
    def exists(path: Path) -> bool:
        """Check if a checkpoint file exists."""
        return path.exists() and path.is_file()
