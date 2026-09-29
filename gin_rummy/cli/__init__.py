"""Terminal interface for Gin Rummy.

- render: colours, hands, the table, round results
- prompts: card choice, the opening discard, a human's turn
- round: the AI's turn on screen, and a round vs AI or player vs player
- app: main
"""

from gin_rummy.cli.app import main

__all__ = ["main"]
