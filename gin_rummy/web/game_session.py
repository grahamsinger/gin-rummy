"""Game session wrapper for web UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gin_rummy.ai import BasicAI, ContextAwareAI, StatisticalAI, DrawChoice
from gin_rummy.database import GameTracker
from gin_rummy.game import Game, GamePhase, InvalidActionError, RoundResult
from gin_rummy.game_runner import execute_ai_turn, TurnResult
from gin_rummy.models import Card, Suit, Rank


# Map for converting card IDs to Card objects
RANK_MAP = {
    'A': Rank.ACE, '2': Rank.TWO, '3': Rank.THREE, '4': Rank.FOUR,
    '5': Rank.FIVE, '6': Rank.SIX, '7': Rank.SEVEN, '8': Rank.EIGHT,
    '9': Rank.NINE, '10': Rank.TEN, 'J': Rank.JACK, 'Q': Rank.QUEEN, 'K': Rank.KING,
}

SUIT_MAP = {
    'S': Suit.SPADES, 'H': Suit.HEARTS, 'D': Suit.DIAMONDS, 'C': Suit.CLUBS,
}

SUIT_NAMES = {
    Suit.SPADES: 'spades',
    Suit.HEARTS: 'hearts',
    Suit.DIAMONDS: 'diamonds',
    Suit.CLUBS: 'clubs',
}

RANK_NAMES = {
    Rank.ACE: 'A', Rank.TWO: '2', Rank.THREE: '3', Rank.FOUR: '4',
    Rank.FIVE: '5', Rank.SIX: '6', Rank.SEVEN: '7', Rank.EIGHT: '8',
    Rank.NINE: '9', Rank.TEN: '10', Rank.JACK: 'J', Rank.QUEEN: 'Q', Rank.KING: 'K',
}


def card_to_id(card: Card) -> str:
    """Convert a Card to a string ID like '7H' or '10S'."""
    return f"{RANK_NAMES[card.rank]}{card.suit.name[0]}"


def id_to_card(card_id: str) -> Card:
    """Convert a string ID like '7H' or '10S' to a Card."""
    # Handle 10 specially
    if card_id.startswith('10'):
        rank_str = '10'
        suit_str = card_id[2]
    else:
        rank_str = card_id[0]
        suit_str = card_id[1]

    rank = RANK_MAP[rank_str]
    suit = SUIT_MAP[suit_str]
    return Card(rank, suit)


def card_to_dict(card: Card) -> dict[str, str]:
    """Convert a Card to a JSON-serializable dict."""
    return {
        'id': card_to_id(card),
        'rank': RANK_NAMES[card.rank],
        'suit': SUIT_NAMES[card.suit],
    }


@dataclass
class HandResultData:
    """Hand data for round result display."""
    cards: list[dict]
    melds: list[dict]
    deadwood: int
    deadwood_cards: list[str]


@dataclass
class RoundResultData:
    """Round result data for JSON serialization."""
    winner: str | None
    points: int
    is_gin: bool
    is_undercut: bool
    is_draw: bool
    player_hand: HandResultData
    opponent_hand: HandResultData
    layoff_cards: list[str] | None = None  # Cards laid off (formatted as strings)
    defender_deadwood_before: int = 0  # Defender's deadwood before layoff


class GameSession:
    """Manages a game session for the web UI."""

    def __init__(self) -> None:
        self.game: Game | None = None
        self.ai: BasicAI | None = None
        self.human_idx: int = 0  # Human is always player 0
        self.last_round_result: RoundResultData | None = None
        self.last_ai_action: dict[str, Any] | None = None  # Structured action data
        self.player_name: str = "You"
        self.ai_difficulty: str = "medium"
        self.tracker: GameTracker = GameTracker()

    def new_game(self, player_name: str | None = None, ai_difficulty: str | None = None) -> dict[str, Any]:
        """Start a new game.

        Args:
            player_name: Player's name (default: "You")
            ai_difficulty: AI difficulty - "easy", "medium", or "hard" (default: "medium")
        """
        # Save settings
        if player_name:
            self.player_name = player_name
        if ai_difficulty:
            self.ai_difficulty = ai_difficulty

        # Create AI based on difficulty
        ai_map = {
            "easy": BasicAI,
            "medium": ContextAwareAI,
            "hard": ContextAwareAI,
        }
        ai_class = ai_map.get(self.ai_difficulty, ContextAwareAI)

        self.game = Game(self.player_name, "Computer")
        self.ai = ai_class()
        self.human_idx = 0
        self.last_round_result = None
        self.last_ai_action = None

        # Start tracking
        self.tracker.start_game(self.player_name, "Computer")

        self.game.deal()
        self.tracker.start_hand(self.game.dealer.name)

        # Handle first discard phase
        # Non-dealer (human if dealer_idx=1, AI if dealer_idx=0) must discard first
        if self.game.current_player_idx != self.human_idx:
            # AI does first discard
            self._ai_first_discard()

        return self.get_state()

    def _ai_first_discard(self) -> None:
        """Handle AI's first discard."""
        if self.game is None or self.ai is None:
            return

        discard = self.ai.decide_discard(self.game.current_player.hand)
        self.game.discard_to_start(discard)
        self.last_ai_action = {
            'type': 'first_discard',
            'discarded': card_to_id(discard),
        }

    def get_state(self) -> dict[str, Any]:
        """Get current game state as JSON-serializable dict."""
        if self.game is None:
            return {'error': 'No game in progress'}

        human = self.game.players[self.human_idx]
        opponent = self.game.players[1 - self.human_idx]

        # Analyze hand for melds
        analysis = human.hand.analyze()

        # Build melds list
        melds = []
        for meld in analysis.melds:
            melds.append({
                'type': 'set' if meld.meld_type.name == 'SET' else 'run',
                'cards': [card_to_id(c) for c in meld.cards],
            })

        # Determine phase string
        phase_map = {
            GamePhase.DEALING: 'dealing',
            GamePhase.FIRST_DISCARD: 'first_discard',
            GamePhase.DRAWING: 'drawing',
            GamePhase.DISCARDING: 'discarding',
            GamePhase.KNOCKED: 'knocked',
            GamePhase.ROUND_OVER: 'round_over',
        }
        phase = phase_map.get(self.game.phase, 'unknown')

        # Is it human's turn?
        your_turn = self.game.current_player_idx == self.human_idx

        # Handle first discard phase
        if self.game.phase == GamePhase.FIRST_DISCARD and your_turn:
            phase = 'discarding'  # Treat as discarding for UI

        # Build message (basic fallback - frontend will handle AI action display)
        if self.game.phase == GamePhase.ROUND_OVER:
            message = "Round over!"
        elif self.game.phase == GamePhase.FIRST_DISCARD:
            if your_turn:
                message = "Discard one card to start the round"
            else:
                message = "Computer is starting..."
        elif your_turn:
            if phase == 'drawing':
                message = "Your turn - click deck or discard pile to draw"
            else:
                message = "Choose a card to discard"
        else:
            message = "Computer's turn..."

        # Assist info
        context = self.game.get_game_context(self.human_idx)
        dead_cards = sorted(context.dead_cards, key=lambda c: (c.suit.value, c.rank.value))
        opponent_known = sorted(
            context.known_cards.opponent_hand_known if context.known_cards else [],
            key=lambda c: (c.suit.value, c.rank.value)
        )

        state = {
            'phase': phase,
            'your_turn': your_turn,
            'hand': [card_to_dict(c) for c in human.hand],
            'melds': melds,
            'deadwood': analysis.deadwood_value,
            'deadwood_cards': [card_to_id(c) for c in analysis.deadwood_cards],
            'discard_top': card_to_dict(self.game.top_of_discard) if self.game.top_of_discard else None,
            'deck_remaining': len(self.game.deck),
            'opponent_card_count': len(opponent.hand),
            'scores': {
                human.name: human.score,
                opponent.name: opponent.score,
            },
            'can_knock': self.game.can_knock and your_turn and phase == 'discarding',
            'message': message,
            'round_over': self.game.phase == GamePhase.ROUND_OVER,
            'round_result': self._round_result_to_dict() if self.last_round_result else None,
            'ai_action': self.last_ai_action,  # Structured AI action data for frontend
            'assist': {
                'dead_cards': [str(c) for c in dead_cards],  # Use suit symbols
                'opponent_known': [str(c) for c in opponent_known],  # Use suit symbols
            },
        }

        return state

    def _round_result_to_dict(self) -> dict[str, Any] | None:
        """Convert round result to dict."""
        if not self.last_round_result:
            return None

        def hand_data_to_dict(hd: HandResultData) -> dict:
            return {
                'cards': hd.cards,
                'melds': hd.melds,
                'deadwood': hd.deadwood,
                'deadwood_cards': hd.deadwood_cards,
            }

        return {
            'winner': self.last_round_result.winner,
            'points': self.last_round_result.points,
            'is_gin': self.last_round_result.is_gin,
            'is_undercut': self.last_round_result.is_undercut,
            'is_draw': self.last_round_result.is_draw,
            'player_hand': hand_data_to_dict(self.last_round_result.player_hand),
            'opponent_hand': hand_data_to_dict(self.last_round_result.opponent_hand),
            'layoff_cards': self.last_round_result.layoff_cards,
            'defender_deadwood_before': self.last_round_result.defender_deadwood_before,
        }

    def draw(self, source: str) -> dict[str, Any]:
        """Draw a card from deck or discard."""
        if self.game is None:
            return {'error': 'No game in progress'}

        if self.game.current_player_idx != self.human_idx:
            return {'error': "Not your turn"}

        if self.game.phase != GamePhase.DRAWING:
            return {'error': f"Cannot draw in {self.game.phase.name} phase"}

        try:
            if source == 'discard':
                if not self.game.top_of_discard:
                    return {'error': 'Discard pile is empty'}
                card = self.game.draw_from_discard()
            else:
                card = self.game.draw_from_deck()

            return self.get_state()

        except InvalidActionError as e:
            return {'error': str(e)}

    def discard(self, card_id: str, knock: bool | None = None) -> dict[str, Any]:
        """Discard a card, optionally knocking.

        Args:
            card_id: The card to discard (e.g., "7H", "10S").
            knock: If None, preview and return can_knock_after info.
                   If True, discard and knock. If False, just discard.

        Returns:
            Game state dict. If knock=None and player can knock,
            returns 'needs_knock_decision', 'post_discard_deadwood', 'discard_card'.
        """
        if self.game is None:
            return {'error': 'No game in progress'}

        if self.game.current_player_idx != self.human_idx:
            return {'error': "Not your turn"}

        try:
            card = id_to_card(card_id)
            human = self.game.players[self.human_idx]

            # Handle first discard phase (no knock possible)
            if self.game.phase == GamePhase.FIRST_DISCARD:
                self.game.discard_to_start(card)
                return self.get_state()

            if self.game.phase != GamePhase.DISCARDING:
                return {'error': f"Cannot discard in {self.game.phase.name} phase"}

            # Calculate post-discard deadwood
            remaining_cards = [c for c in human.hand if c != card]
            from gin_rummy.models import analyze_hand
            post_analysis = analyze_hand(remaining_cards)
            post_discard_deadwood = post_analysis.deadwood_value
            can_knock_after = post_discard_deadwood <= self.game.knock_threshold

            # If knock decision not yet made and can knock, ask user
            if knock is None and can_knock_after:
                state = self.get_state()
                state['needs_knock_decision'] = True
                state['post_discard_deadwood'] = post_discard_deadwood
                state['discard_card'] = card_id
                return state

            if knock and can_knock_after:
                # Discard the card manually, then knock
                human.hand.remove(card)
                self.game.discard_pile.append(card)
                self.game._discard_history.append(card)

                result = self.game.knock()
                self._save_round_result(result)
                return self.get_state()

            # Just discard (no knock or can't knock)
            self.game.discard(card)
            return self.get_state()

        except (InvalidActionError, KeyError, ValueError) as e:
            return {'error': str(e)}

    def knock(self) -> dict[str, Any]:
        """Knock to end the round."""
        if self.game is None:
            return {'error': 'No game in progress'}

        if self.game.current_player_idx != self.human_idx:
            return {'error': "Not your turn"}

        if self.game.phase != GamePhase.DISCARDING:
            return {'error': 'Can only knock during discard phase'}

        try:
            result = self.game.knock()
            self._save_round_result(result)
            return self.get_state()

        except InvalidActionError as e:
            return {'error': str(e)}

    def ai_turn(self) -> dict[str, Any]:
        """Execute AI's turn."""
        if self.game is None or self.ai is None:
            return {'error': 'No game in progress'}

        if self.game.current_player_idx == self.human_idx:
            return {'error': "It's your turn, not AI's"}

        # Handle first discard if needed
        if self.game.phase == GamePhase.FIRST_DISCARD:
            self._ai_first_discard()
            return self.get_state()

        if self.game.phase not in (GamePhase.DRAWING, GamePhase.DISCARDING):
            return {'error': f"Cannot play in {self.game.phase.name} phase"}

        # Execute AI turn
        turn_result, actions, round_result = execute_ai_turn(self.game, self.ai)

        if turn_result == TurnResult.DRAW:
            # Deck exhausted
            self.last_round_result = RoundResultData(
                winner=None,
                points=0,
                is_gin=False,
                is_undercut=False,
                is_draw=True,
                player_hand=self._build_hand_result(self.human_idx),
                opponent_hand=self._build_hand_result(1 - self.human_idx),
            )
            self.game.phase = GamePhase.ROUND_OVER
            # Record draw in database
            self.tracker.end_hand(
                winner_name=None,
                loser_name=None,
                points=0,
                is_draw=True,
                knocker_name=None,
                winner_deadwood=0,
                loser_deadwood=0
            )
        elif turn_result == TurnResult.KNOCKED and round_result:
            self._save_round_result(round_result)
        elif actions:
            # Build structured action data for frontend to display sequentially
            self.last_ai_action = {
                'type': 'turn',
                'draw_from': 'discard' if actions.draw_source == DrawChoice.DISCARD else 'deck',
                'drew_card': card_to_id(actions.drawn_card) if actions.draw_source == DrawChoice.DISCARD else None,
                'discarded': card_to_id(actions.discarded_card),
            }

        return self.get_state()

    def _build_hand_result(self, player_idx: int) -> HandResultData:
        """Build hand result data with melds and deadwood."""
        if self.game is None:
            return HandResultData(cards=[], melds=[], deadwood=0, deadwood_cards=[])

        hand = self.game.players[player_idx].hand
        analysis = hand.analyze()

        melds = []
        for meld in analysis.melds:
            melds.append({
                'type': 'set' if meld.meld_type.name == 'SET' else 'run',
                'cards': [card_to_id(c) for c in meld.cards],
            })

        return HandResultData(
            cards=[card_to_dict(c) for c in hand],
            melds=melds,
            deadwood=analysis.deadwood_value,
            deadwood_cards=[card_to_id(c) for c in analysis.deadwood_cards],
        )

    def _save_round_result(self, result: RoundResult) -> None:
        """Save round result for display."""
        if self.game is None:
            return

        winner_name = result.winner.name if result.winner else None
        loser_name = result.loser.name if result.loser else None
        knocker_name = result.knocker.name if result.knocker else None

        # Convert layoff cards to string format
        layoff_cards_str = None
        if result.layoff_cards:
            layoff_cards_str = [card_to_id(c) for c in result.layoff_cards]

        self.last_round_result = RoundResultData(
            winner=winner_name,
            points=result.points,
            is_gin=result.is_gin,
            is_undercut=result.is_undercut,
            is_draw=result.is_draw,
            player_hand=self._build_hand_result(self.human_idx),
            opponent_hand=self._build_hand_result(1 - self.human_idx),
            layoff_cards=layoff_cards_str,
            defender_deadwood_before=result.defender_deadwood_before_layoff,
        )

        # Record hand result in database
        self.tracker.end_hand(
            winner_name=winner_name,
            loser_name=loser_name,
            points=result.points,
            is_gin=result.is_gin,
            is_undercut=result.is_undercut,
            is_draw=result.is_draw,
            knocker_name=knocker_name,
            winner_deadwood=result.winner_deadwood,
            loser_deadwood=result.loser_deadwood,
        )

    def new_round(self) -> dict[str, Any]:
        """Start a new round."""
        if self.game is None:
            return {'error': 'No game in progress'}

        self.game.new_round()
        self.game.deal()
        self.tracker.start_hand(self.game.dealer.name)

        # Reset AI state with same difficulty
        ai_map = {
            "easy": BasicAI,
            "medium": ContextAwareAI,
            "hard": ContextAwareAI,
        }
        ai_class = ai_map.get(self.ai_difficulty, ContextAwareAI)
        self.ai = ai_class()

        self.last_round_result = None
        self.last_ai_action = None

        # Handle first discard
        if self.game.current_player_idx != self.human_idx:
            self._ai_first_discard()

        return self.get_state()
