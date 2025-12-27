"""Player class for Gin Rummy."""

from gin_rummy.models.hand import Hand


class Player:
    """A Gin Rummy player with name, hand, and score."""

    def __init__(self, name: str) -> None:
        """Create a player with the given name.

        Args:
            name: Display name for the player.
        """
        self.name = name
        self.hand = Hand()
        self.score = 0

    def reset_hand(self) -> None:
        """Clear the player's hand for a new round."""
        self.hand = Hand()

    def __repr__(self) -> str:
        return f"Player({self.name!r})"
