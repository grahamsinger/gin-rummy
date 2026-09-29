"""Terminal rendering: colours, hands, the table and round results."""

from __future__ import annotations

import os

from gin_rummy.config import get_config
from gin_rummy.game import Game, RoundResult
from gin_rummy.models import Card, Hand, MeldType, Suit

# ANSI color codes for terminal output
RED = "\033[91m"  # Bright red for hearts/diamonds
RESET = "\033[0m"  # Reset to default

# Unicode superscript digits for card selection numbers
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def superscript(n: int) -> str:
    """Convert a number to Unicode superscript characters."""
    return "".join(SUPERSCRIPTS[int(d)] for d in str(n))


def clear_screen() -> None:
    """Clear the terminal screen if enabled in config."""
    if get_config().display.clear_screen:
        os.system("cls" if os.name == "nt" else "clear")


# Runtime state for assist mode toggle (overrides config)
_assist_show_values: bool | None = None


def toggle_assist_values() -> bool:
    """Toggle assist mode value display. Returns new state."""
    global _assist_show_values
    config = get_config()
    current = config.assist.show_values if _assist_show_values is None else _assist_show_values
    _assist_show_values = not current
    return _assist_show_values


def get_assist_show_values() -> bool:
    """Get current assist show_values state (runtime override or config)."""
    if _assist_show_values is not None:
        return _assist_show_values
    return get_config().assist.show_values


def display_assist_info(game: Game, human_player_idx: int) -> None:
    """Display assist information (opponent known cards and buried discards).

    Args:
        game: The game instance.
        human_player_idx: Index of the human player (0 or 1).
    """
    config = get_config()
    if not config.assist.enabled:
        return

    show_values = get_assist_show_values()
    context = game.get_game_context(human_player_idx)

    print("--- Assist ---")

    # Opponent's known cards (pickups minus re-discards)
    if context.known_cards:
        opponent_known = context.known_cards.opponent_hand_known
        if show_values and opponent_known:
            cards_str = ", ".join(str(c) for c in sorted(opponent_known, key=lambda c: (c.suit.value, c.rank.value)))
            print(f"Opponent has: {cards_str}")
        else:
            count = len(opponent_known)
            print(f"Opponent has: {count} known card{'s' if count != 1 else ''}")

        # Dead cards (buried discards - cards in discard pile that can't be drawn)
        dead = context.dead_cards
        if show_values and dead:
            cards_str = ", ".join(str(c) for c in sorted(dead, key=lambda c: (c.suit.value, c.rank.value)))
            print(f"Dead cards: {cards_str}")
        else:
            print(f"Dead cards: {len(dead)}")
    else:
        # Fallback if known_cards not available
        print(f"Dead cards: {len(context.discard_history)}")

    print("(Press 'a' to toggle card values)")


def display_hand_with_melds(hand: Hand, show_numbers: bool = True, for_discard: bool = False) -> list:
    """Display a hand with melds visually grouped.

    Args:
        hand: The hand to display.
        show_numbers: If True, show card numbers for selection.
        for_discard: If True, order deadwood first for easier discard selection.

    Returns:
        List of cards in display order (for mapping selection numbers).
    """
    analysis = hand.analyze()

    # Build ordered card list: deadwood first if for_discard, otherwise original order
    if for_discard:
        # Deadwood cards first (sorted by value, highest first for easy discard)
        deadwood_sorted = sorted(analysis.deadwood_cards, key=lambda c: -c.deadwood_value)
        melded_cards = [c for c in hand if c not in analysis.deadwood_cards]
        display_cards = deadwood_sorted + melded_cards
    else:
        display_cards = list(hand)

    # Build a mapping from card to its meld (if any)
    card_to_meld: dict = {}
    for meld in analysis.melds:
        for card in meld.cards:
            card_to_meld[card] = meld

    # Display melds
    if analysis.melds:
        print("  Melds:")
        for meld in analysis.melds:
            meld_type = "Set" if meld.meld_type == MeldType.SET else "Run"
            cards_str = " ".join(str(c) for c in meld.cards)
            print(f"    [{meld_type}] {cards_str}")

    # Display deadwood summary
    if analysis.deadwood_cards:
        deadwood_str = " ".join(str(c) for c in sorted(analysis.deadwood_cards, key=lambda c: -c.deadwood_value))
        print(f"  Deadwood ({analysis.deadwood_value}): {deadwood_str}")
    else:
        print("  Deadwood (0): None - GIN!")

    # Display all cards with numbers for selection
    if show_numbers:
        if for_discard:
            print("\n  Choose card to discard (deadwood listed first):")
        else:
            print("\n  All cards:")

        for i, card in enumerate(display_cards, 1):
            marker = "*" if card in card_to_meld else " "
            print(f"  {i:2}.{marker}{card}", end="")
            if i % 5 == 0:
                print()
        if len(display_cards) % 5 != 0:
            print()
        print("  (* = in a meld)")

    return display_cards


def display_hand_by_suit(hand: Hand, show_numbers: bool = True) -> list[Card]:
    """Display a hand grouped by suit with melds in brackets.

    Cards are positioned by rank (A-K) so runs are visually aligned.
    Melded cards are wrapped in brackets. Red suits are colored.

    Args:
        hand: The hand to display.
        show_numbers: If True, show superscript selection numbers.

    Returns:
        List of cards in selection order (for mapping numbers to cards).
    """
    analysis = hand.analyze()

    # Build set of melded cards for quick lookup
    melded_cards: set[Card] = set()
    for meld in analysis.melds:
        melded_cards.update(meld.cards)

    # Group cards by suit
    cards_by_suit: dict[Suit, list[Card]] = {suit: [] for suit in Suit}
    for card in hand:
        cards_by_suit[card.suit].append(card)

    # Sort each suit by rank
    for suit in cards_by_suit:
        cards_by_suit[suit].sort(key=lambda c: c.rank.value)

    # Build selection order list (spades, hearts, diamonds, clubs - by rank within each)
    suit_order = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
    selection_order: list[Card] = []
    for suit in suit_order:
        selection_order.extend(cards_by_suit[suit])

    # Create card to selection number mapping
    card_to_num: dict[Card, int] = {card: i + 1 for i, card in enumerate(selection_order)}

    # Column width for each rank position (A, 2, 3, ..., K)
    # Reduced for more compact display
    col_width = 3

    # Display each suit row
    for suit in suit_order:
        suit_cards = cards_by_suit[suit]
        if not suit_cards:
            continue

        # Build the row string with cards at their rank positions
        # Track which positions have cards and which are in melds
        row_parts: list[str] = []
        row_parts.append(f"{suit.symbol}: ")

        # Find meld groups (consecutive melded cards)
        meld_groups: list[list[Card]] = []
        current_group: list[Card] = []
        for card in suit_cards:
            if card in melded_cards:
                current_group.append(card)
            else:
                if current_group:
                    meld_groups.append(current_group)
                    current_group = []
        if current_group:
            meld_groups.append(current_group)

        # Build positions array (13 positions for A-K)
        positions: list[str] = [""] * 13
        in_meld_group: list[bool] = [False] * 13

        for card in suit_cards:
            pos = card.rank.value - 1  # 0-indexed
            num_str = superscript(card_to_num[card]) if show_numbers else ""
            card_str = card.colored_str(RED, RESET) + num_str
            positions[pos] = card_str
            in_meld_group[pos] = card in melded_cards

        # Build row with brackets around meld groups
        row = f"{suit.symbol}: "
        i = 0
        while i < 13:
            if positions[i]:
                # Check if this starts a meld group
                if in_meld_group[i]:
                    # Find end of meld group
                    group_start = i
                    while i < 13 and in_meld_group[i] and positions[i]:
                        i += 1
                    group_end = i

                    # Add opening bracket
                    row += "["
                    for j in range(group_start, group_end):
                        row += positions[j]
                        if j < group_end - 1:
                            row += " "
                    row += "] "
                else:
                    row += positions[i] + " "
                    i += 1
            else:
                # Empty position - add spacing based on rank
                row += " " * col_width
                i += 1

        print(f"  {row.rstrip()}")

    # Print deadwood total
    print(f"\n  Deadwood: {analysis.deadwood_value}")

    return selection_order


def display_game_state(
    game: Game, human_player_idx: int, show_opponent: bool = False, turn_player_name: str | None = None
) -> None:
    """Display the current game state from human player's perspective.

    Args:
        game: The game instance.
        human_player_idx: Index of the human player (0 or 1).
        show_opponent: If True, show opponent's cards (for debugging).
        turn_player_name: If provided, show whose turn it is at the top.
    """
    human = game.players[human_player_idx]
    opponent = game.players[1 - human_player_idx]

    print("\n" + "=" * 50)
    print("              GIN RUMMY")
    print("=" * 50)

    # Turn indicator
    if turn_player_name:
        print(f"\n>>> {turn_player_name}'s turn <<<")

    # Scores
    print(f"\nScores: {human.name}: {human.score}  |  {opponent.name}: {opponent.score}")

    # Opponent info
    print(f"\n{opponent.name} has {len(opponent.hand)} cards")
    if show_opponent:
        opponent.hand.sort()
        print(f"  (DEBUG: {opponent.hand})")

    print(f"Deck: {len(game.deck)} cards")

    # Discard pile
    if game.top_of_discard:
        print(f"Discard pile: {game.top_of_discard}")
    else:
        print("Discard pile: (empty)")

    # Assist mode info
    display_assist_info(game, human_player_idx)

    # Human player's hand with meld analysis
    print(f"\n{human.name}'s hand:")
    display_hand_by_suit(human.hand, show_numbers=False)

    print()


def display_round_result(game: Game, result: RoundResult | None = None) -> None:
    """Display the result of a round."""
    print("\n" + "=" * 50)
    print("           ROUND OVER")
    print("=" * 50)

    # Show both hands with melds
    for player in game.players:
        print(f"\n{player.name}'s hand:")
        display_hand_by_suit(player.hand, show_numbers=False)

    # Display layoff information if cards were laid off
    if result and result.layoff_cards:
        defender = result.loser if result.winner == result.knocker else result.winner
        layoff_str = " ".join(str(c) for c in result.layoff_cards)
        print(f"\n{defender.name} laid off: {layoff_str}")
        print(
            f"  (Deadwood: {result.defender_deadwood_before_layoff} → "
            f"{result.defender_deadwood_before_layoff - sum(c.deadwood_value for c in result.layoff_cards)})"
        )

    # Show result summary
    if result:
        if result.is_gin:
            print(f"\n{result.knocker.name} gets GIN!")
        elif result.is_undercut:
            print(f"\n{result.winner.name} UNDERCUTS!")
        elif result.knocker:
            print(f"\n{result.knocker.name} knocks.")

        if result.winner:
            print(f"{result.winner.name} wins {result.points} points!")

    print(
        f"\nScores: {game.players[0].name}: {game.players[0].score}  |  {game.players[1].name}: {game.players[1].score}"
    )
