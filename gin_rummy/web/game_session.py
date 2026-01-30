"""Game session wrapper for web UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from gin_rummy.ai import BasicAI, ContextAwareAI, StatisticalAI, DrawChoice
from gin_rummy.database import GameTracker, card_to_db_str, cards_to_db_list
from gin_rummy.game import Game, GamePhase, InvalidActionError, RoundResult
from gin_rummy.game_runner import execute_ai_turn, TurnResult
from gin_rummy.models import Card, Suit, Rank, analyze_hand


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


def calculate_card_helpfulness(hand: list[Card], dead_cards: frozenset[Card]) -> dict[str, Any]:
    """Calculate how helpful each non-hand card would be.

    Simulates drawing a card and then discarding optimally to see if deadwood improves.

    Args:
        hand: Current cards in hand
        dead_cards: Cards that are known dead (in discard pile)

    Returns:
        Dict with:
        - helpful_cards: List of {card, reduction, is_dead} sorted by reduction (descending)
        - total_helpful: Count of all cards that would help
        - live_helpful: Count of helpful cards that are not dead
    """
    # Calculate current deadwood
    current_analysis = analyze_hand(hand)
    current_deadwood = current_analysis.deadwood_value

    helpful_cards = []

    # Check every card not in hand
    for suit in Suit:
        for rank in Rank:
            card = Card(rank, suit)
            if card in hand:
                continue

            # Simulate drawing this card (now have 11 cards)
            test_hand_11 = hand + [card]
            test_analysis_11 = analyze_hand(test_hand_11)

            # Find the best card to discard (highest deadwood value from non-melded cards)
            # After optimal discard, we'd have 10 cards again
            used_cards = set()
            for meld in test_analysis_11.melds:
                used_cards.update(meld.cards)

            # Deadwood cards are those not in any meld
            deadwood_cards = [c for c in test_hand_11 if c not in used_cards]

            if not deadwood_cards:
                # Perfect hand - all cards melded (gin!)
                # Discard the least valuable melded card
                worst_card = min(test_hand_11, key=lambda c: c.deadwood_value)
            else:
                # Discard the worst deadwood card
                worst_card = max(deadwood_cards, key=lambda c: c.deadwood_value)

            # Calculate deadwood after optimal discard
            final_hand = [c for c in test_hand_11 if c != worst_card]
            final_analysis = analyze_hand(final_hand)
            new_deadwood = final_analysis.deadwood_value

            # Calculate reduction (positive = helpful)
            reduction = current_deadwood - new_deadwood

            # Only include cards that help (positive reduction)
            if reduction > 0:
                is_dead = card in dead_cards

                # Check if this card completes a meld (not just reduces deadwood)
                completes_meld = False
                for meld in test_analysis_11.melds:
                    if card in meld.cards:
                        # Check if this meld is new (wasn't possible without this card)
                        meld_cards_set = set(meld.cards)
                        is_new_meld = not any(
                            set(m.cards) == meld_cards_set
                            for m in current_analysis.melds
                        )
                        if is_new_meld:
                            completes_meld = True
                            break

                helpful_cards.append({
                    'card': str(card),  # Format with suit symbols
                    'card_id': card_to_id(card),  # ASCII format for frontend
                    'reduction': reduction,
                    'is_dead': is_dead,
                    'completes_meld': completes_meld,
                })

    # Sort by reduction (most helpful first)
    helpful_cards.sort(key=lambda x: x['reduction'], reverse=True)

    # Count totals
    total_helpful = len(helpful_cards)
    live_helpful = sum(1 for c in helpful_cards if not c['is_dead'])

    return {
        'helpful_cards': helpful_cards,
        'total_helpful': total_helpful,
        'live_helpful': live_helpful,
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
        self.player_name: str = ""  # Will be set by new_game() or generated
        self.ai_difficulty: str = "medium"
        self.game_mode: str = "practice"  # "practice" or "target"
        self.target_score: int | None = None  # Target score for "target" mode
        self.oklahoma_gin: bool = False
        self.spade_doubling: bool = True  # Default ON
        self.match_mode: bool = False
        self.games_won: dict[str, int] = {}
        self.match_winner: str | None = None
        self.game_over: bool = False
        self.winner: str | None = None
        self.tracker: GameTracker = GameTracker()

        # Turn tracking state (for recording to database)
        self.turn_cards_before: list[str] | None = None
        self.turn_deadwood_before: int | None = None
        self.turn_drew_from: str | None = None  # 'deck' or 'discard'
        self.turn_card_drawn: Card | None = None

        # Deferred DB tracking - don't create game/hand until human makes first move
        self.db_game_started: bool = False
        self.buffered_ai_turns: list[dict] = []
        self.pending_dealer_name: str = ""

    def new_game(
        self,
        player_name: str | None = None,
        ai_difficulty: str | None = None,
        game_mode: str | None = None,
        target_score: int | None = None,
        oklahoma_gin: bool | None = None,
        spade_doubling: bool | None = None,
        match_mode: bool | None = None,
    ) -> dict[str, Any]:
        """Start a new game.

        Args:
            player_name: Player's name (default: "You")
            ai_difficulty: AI difficulty - "easy", "medium", or "hard" (default: "medium")
            game_mode: Game mode - "practice" or "target" (default: "practice")
            target_score: Target score for "target" mode (100, 150, 200, 250)
            oklahoma_gin: Whether to use Oklahoma Gin rules
            spade_doubling: Whether to double points when upcard is a spade
            match_mode: Whether to play best-of-3 match
        """
        # Save settings
        if player_name:
            self.player_name = player_name
        elif not self.player_name:
            # Fallback: generate on server side (shouldn't happen normally)
            import secrets
            self.player_name = f"Guest_{secrets.token_hex(2)}"
        if ai_difficulty:
            self.ai_difficulty = ai_difficulty
        if game_mode:
            self.game_mode = game_mode
        if target_score is not None:
            self.target_score = target_score
        if oklahoma_gin is not None:
            self.oklahoma_gin = oklahoma_gin
        if spade_doubling is not None:
            self.spade_doubling = spade_doubling
        if match_mode is not None:
            # Only reset match tracking when starting a NEW match
            # (not when continuing an existing match)
            if match_mode and not self.match_mode:
                # Starting a new match
                self.games_won = {self.player_name: 0, "Computer": 0}
                self.match_winner = None
            elif not match_mode:
                # Turning off match mode
                self.games_won = {}
                self.match_winner = None
            # If match_mode=True and already in match mode, preserve games_won
            self.match_mode = match_mode

        # Reset game over state (but preserve match tracking)
        self.game_over = False
        self.winner = None

        # Create AI based on difficulty
        ai_map = {
            "easy": BasicAI,
            "medium": ContextAwareAI,
            "hard": ContextAwareAI,
        }
        ai_class = ai_map.get(self.ai_difficulty, ContextAwareAI)

        self.game = Game(
            self.player_name,
            "Computer",
            is_oklahoma_gin=self.oklahoma_gin,
            spade_doubling_enabled=self.spade_doubling,
        )
        self.ai = ai_class()
        self.human_idx = 0
        self.last_round_result = None
        self.last_ai_action = None

        # Reset deferred DB tracking - don't create game until human makes first move
        self.db_game_started = False
        self.buffered_ai_turns = []

        self.game.deal()
        self.pending_dealer_name = self.game.dealer.name

        # Handle first discard phase (only in standard mode)
        # Non-dealer (human if dealer_idx=1, AI if dealer_idx=0) must discard first
        # In Oklahoma mode, phase is DRAWING so this is skipped
        if self.game.phase == GamePhase.FIRST_DISCARD and self.game.current_player_idx != self.human_idx:
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

    def _ensure_db_started(self) -> None:
        """Start game/hand in DB if not already started, and flush buffered AI turns."""
        if self.db_game_started or self.game is None:
            return

        # Start game and hand in database
        self.tracker.start_game(
            self.player_name,
            "Computer",
            oklahoma_gin=self.oklahoma_gin,
            spade_doubling=self.spade_doubling,
            game_mode=self.game_mode,
            target_score=self.target_score,
            ai_difficulty=self.ai_difficulty,
            match_mode=self.match_mode,
        )
        self.tracker.start_hand(self.pending_dealer_name)

        # Flush any buffered AI turns (including reasoning if captured)
        for turn_data in self.buffered_ai_turns:
            # Pop reasoning before recording turn (not a DB field)
            reasoning = turn_data.pop('_reasoning', None)
            turn_id = self.tracker.record_turn(**turn_data)
            # Record AI decisions if reasoning was captured
            if reasoning:
                self._record_ai_decisions(turn_id, reasoning)
        self.buffered_ai_turns = []

        self.db_game_started = True

    def _record_ai_decisions(self, turn_id: int, reasoning: Any) -> None:
        """Record AI decision reasoning to the database.

        Args:
            turn_id: The turn ID to associate decisions with.
            reasoning: TurnReasoning object with draw, discard, and knock decisions.
        """
        from gin_rummy.ai import TurnReasoning

        if not isinstance(reasoning, TurnReasoning):
            return

        # Record draw decision
        if reasoning.draw:
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type='draw',
                choice=reasoning.draw.choice.name,
                reasoning=reasoning.draw.reasoning,
                options_considered=reasoning.draw.factors,
            )

        # Record discard decision
        if reasoning.discard:
            # Include both factors and options_considered
            options = reasoning.discard.factors.copy()
            for card_str, dw in reasoning.discard.options_considered:
                options.append(f"{card_str} → dw={dw}")
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type='discard',
                choice=str(reasoning.discard.card),
                reasoning=reasoning.discard.reasoning,
                options_considered=options,
            )

        # Record knock decision
        if reasoning.knock:
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type='knock',
                choice='knock' if reasoning.knock.should_knock else 'no_knock',
                reasoning=reasoning.knock.reasoning,
                options_considered=reasoning.knock.factors,
            )

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

        # Calculate card helpfulness
        helpfulness = calculate_card_helpfulness(
            list(human.hand),
            context.known_cards.dead_cards if context.known_cards else frozenset()
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
                'helpfulness': helpfulness,  # Card helpfulness ranking
            },
            'game_mode': self.game_mode,
            'target_score': self.target_score,
            'game_over': self.game_over,
            'game_winner': self.winner,
            'oklahoma_gin': self.oklahoma_gin,
            'spade_doubling': self.spade_doubling,
            'knock_threshold': self.game.knock_threshold,
            'upcard': card_to_dict(self.game.upcard) if self.game.upcard else None,
            'match_mode': self.match_mode,
            'games_won': self.games_won if self.match_mode else None,
            'match_winner': self.match_winner if self.match_mode else None,
            'player_name': self.player_name,
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
            human = self.game.players[self.human_idx]

            # Save turn state BEFORE drawing
            self.turn_cards_before = cards_to_db_list(list(human.hand))
            analysis_before = human.hand.analyze()
            self.turn_deadwood_before = analysis_before.deadwood_value

            # Draw the card
            if source == 'discard':
                if not self.game.top_of_discard:
                    return {'error': 'Discard pile is empty'}
                card = self.game.draw_from_discard()
                self.turn_drew_from = 'discard'
            else:
                card = self.game.draw_from_deck()
                self.turn_drew_from = 'deck'

            self.turn_card_drawn = card

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

            # Automatic gin detection: 0 deadwood always knocks
            if knock is None and post_discard_deadwood == 0:
                knock = True

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

                # Ensure DB started before recording turn
                self._ensure_db_started()

                # Record turn with knock
                if (self.turn_cards_before is not None and
                    self.turn_deadwood_before is not None and
                    self.turn_drew_from and
                    self.turn_card_drawn):
                    cards_after = cards_to_db_list(list(human.hand))
                    self.tracker.record_turn(
                        player_name=human.name,
                        drew_from=self.turn_drew_from,
                        card_drawn=card_to_db_str(self.turn_card_drawn),
                        card_discarded=card_to_db_str(card),
                        did_knock=True,
                        cards_before=self.turn_cards_before,
                        cards_after=cards_after,
                        deadwood_before=self.turn_deadwood_before,
                        deadwood_after=post_discard_deadwood
                    )

                result = self.game.knock()
                self._save_round_result(result)
                return self.get_state()

            # Just discard (no knock or can't knock)
            self.game.discard(card)

            # Ensure DB started before recording turn
            self._ensure_db_started()

            # Record turn without knock
            if (self.turn_cards_before is not None and
                self.turn_deadwood_before is not None and
                self.turn_drew_from and
                self.turn_card_drawn):
                cards_after = cards_to_db_list(list(human.hand))
                deadwood_after = human.hand.analyze().deadwood_value
                self.tracker.record_turn(
                    player_name=human.name,
                    drew_from=self.turn_drew_from,
                    card_drawn=card_to_db_str(self.turn_card_drawn),
                    card_discarded=card_to_db_str(card),
                    did_knock=False,
                    cards_before=self.turn_cards_before,
                    cards_after=cards_after,
                    deadwood_before=self.turn_deadwood_before,
                    deadwood_after=deadwood_after
                )

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

        # Save AI player state before turn (for tracking)
        ai_player = self.game.players[1 - self.human_idx]
        cards_before = cards_to_db_list(list(ai_player.hand))
        deadwood_before = ai_player.hand.analyze().deadwood_value

        # Execute AI turn with reasoning capture
        turn_result, actions, round_result = execute_ai_turn(
            self.game, self.ai, capture_reasoning=True
        )

        # Build AI action first (before checking result type) so it's available for round result modal
        if actions:
            self.last_ai_action = {
                'type': 'turn',
                'draw_from': 'discard' if actions.draw_source == DrawChoice.DISCARD else 'deck',
                'drew_card': card_to_id(actions.drawn_card) if actions.draw_source == DrawChoice.DISCARD else None,
                'discarded': card_to_id(actions.discarded_card),
            }

            # Prepare turn data for recording
            drew_from = 'discard' if actions.draw_source == DrawChoice.DISCARD else 'deck'
            if actions.did_knock:
                # Cards after knock (discarded card removed)
                cards_after = cards_to_db_list([c for c in ai_player.hand if c != actions.discarded_card])
            else:
                cards_after = cards_to_db_list(list(ai_player.hand))

            turn_data = {
                'player_name': ai_player.name,
                'drew_from': drew_from,
                'card_drawn': card_to_db_str(actions.drawn_card),
                'card_discarded': card_to_db_str(actions.discarded_card),
                'did_knock': actions.did_knock,
                'cards_before': cards_before,
                'cards_after': cards_after,
                'deadwood_before': deadwood_before,
                'deadwood_after': actions.deadwood_after,
            }

            # Buffer AI turn if DB not started, otherwise record directly
            if self.db_game_started:
                turn_id = self.tracker.record_turn(**turn_data)
                # Record AI decisions if reasoning was captured
                if actions.reasoning:
                    self._record_ai_decisions(turn_id, actions.reasoning)
            else:
                # Buffer turn data along with reasoning for later recording
                turn_data['_reasoning'] = actions.reasoning
                self.buffered_ai_turns.append(turn_data)

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
            # Record draw in database only if game was started (human played)
            if self.db_game_started:
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

        # Check if game is over (target score reached)
        if self.game_mode == "target" and self.target_score is not None:
            player_score = self.game.players[self.human_idx].score
            ai_score = self.game.players[1 - self.human_idx].score

            game_winner = None
            if player_score >= self.target_score:
                game_winner = self.player_name
            elif ai_score >= self.target_score:
                game_winner = "Computer"

            if game_winner:
                if self.match_mode:
                    # Match play - track games won
                    self.games_won[game_winner] += 1
                    if self.games_won[game_winner] >= 2:
                        # Match is over
                        self.match_winner = game_winner
                        self.game_over = True
                        self.winner = game_winner
                        if self.db_game_started:
                            self.tracker.end_game(game_winner, player_score, ai_score)
                    else:
                        # Game over but match continues
                        self.game_over = True
                        self.winner = game_winner
                        # Don't call tracker.end_game yet - match not complete
                else:
                    # Standard mode - game over is final
                    self.game_over = True
                    self.winner = game_winner
                    if self.db_game_started:
                        self.tracker.end_game(game_winner, player_score, ai_score)

        # Record hand result in database only if game was started (human played)
        if self.db_game_started:
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

        # Don't start a new round if the game is over
        if self.game_over:
            return self.get_state()

        self.game.new_round()
        self.game.deal()

        # If DB already started, start new hand immediately
        # Otherwise, store dealer name for deferred start
        if self.db_game_started:
            self.tracker.start_hand(self.game.dealer.name)
        else:
            self.pending_dealer_name = self.game.dealer.name
            self.buffered_ai_turns = []

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

        # Reset turn tracking state
        self.turn_cards_before = None
        self.turn_deadwood_before = None
        self.turn_drew_from = None
        self.turn_card_drawn = None

        # Handle first discard (only in standard mode)
        # In Oklahoma mode, phase is DRAWING so this is skipped
        if self.game.phase == GamePhase.FIRST_DISCARD and self.game.current_player_idx != self.human_idx:
            self._ai_first_discard()

        return self.get_state()
