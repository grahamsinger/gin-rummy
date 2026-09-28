"""Game session wrapper for web UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gin_rummy.ai import BasicAI, DIFFICULTY_TO_AI, DrawChoice, MonteCarloAI, make_ai
from gin_rummy.database import GameTracker, get_connection, get_resumable_game
from gin_rummy.game import Game, GamePhase, InvalidActionError, RoundResult
from gin_rummy.game_runner import execute_ai_turn, TurnResult
from gin_rummy.models import Card, Suit, Rank, analyze_hand
from gin_rummy.models.hand import CardNotInHandError


def card_to_dict(card: Card) -> dict[str, str]:
    """Convert a Card to a JSON-serializable dict ({"id": "7H", "rank": "7", "suit": "hearts"})."""
    return {"id": card.code, "rank": card.rank.short_name, "suit": card.suit.value}


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
                        is_new_meld = not any(set(m.cards) == meld_cards_set for m in current_analysis.melds)
                        if is_new_meld:
                            completes_meld = True
                            break

                helpful_cards.append(
                    {
                        "card": str(card),  # Format with suit symbols
                        "card_id": card.code,  # ASCII format for frontend
                        "reduction": reduction,
                        "is_dead": is_dead,
                        "completes_meld": completes_meld,
                    }
                )

    # Sort by reduction (most helpful first)
    helpful_cards.sort(key=lambda x: x["reduction"], reverse=True)

    # Count totals
    total_helpful = len(helpful_cards)
    live_helpful = sum(1 for c in helpful_cards if not c["is_dead"])

    return {
        "helpful_cards": helpful_cards,
        "total_helpful": total_helpful,
        "live_helpful": live_helpful,
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
        self.match_id: int | None = None
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

        # Scenario quiz state (created lazily by the /api/scenario endpoints)
        self.scenario_session = None

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
            # (not when continuing an existing match). A finished match
            # (match_winner set) also starts fresh - otherwise "Play Again"
            # carries the old tally and the new match ends after one game.
            if match_mode and (not self.match_mode or self.match_winner is not None):
                # Starting a new match - generate a new match_id
                self.games_won = {self.player_name: 0, "Computer": 0}
                self.match_winner = None
                with get_connection() as conn:
                    row = conn.execute("SELECT COALESCE(MAX(match_id), 0) + 1 FROM games").fetchone()
                    self.match_id = row[0]
            elif match_mode and self.player_name not in self.games_won:
                # Player renamed mid-match - re-key their tally
                old_names = [n for n in self.games_won if n != "Computer"]
                old_wins = self.games_won.pop(old_names[0], 0) if old_names else 0
                self.games_won[self.player_name] = old_wins
            elif not match_mode:
                # Turning off match mode
                self.games_won = {}
                self.match_winner = None
                self.match_id = None
            # If match_mode=True and already in match mode, preserve games_won and match_id
            self.match_mode = match_mode

        # Reset game over state (but preserve match tracking)
        self.game_over = False
        self.winner = None

        # Create AI based on difficulty

        self.game = Game(
            self.player_name,
            "Computer",
            is_oklahoma_gin=self.oklahoma_gin,
            spade_doubling_enabled=self.spade_doubling,
        )
        self.ai = make_ai(DIFFICULTY_TO_AI.get(self.ai_difficulty, "context"))
        self.human_idx = 0
        self.last_round_result = None
        self.last_ai_action = None

        # Reset deferred DB tracking - don't create game until human makes first move
        self.db_game_started = False
        self.buffered_ai_turns = []

        self.game.deal()
        self.pending_dealer_name = self.game.dealer.name

        return self.get_state()

    def resume_game(self, game_id: int) -> dict[str, Any]:
        """Resume an incomplete game from the database.

        Restores game settings and cumulative scores, deals a fresh hand.
        The interrupted mid-hand state is abandoned.

        Args:
            game_id: The database game ID to resume.

        Returns:
            Game state dict, or error dict if game can't be resumed.
        """
        data = get_resumable_game(game_id)
        if data is None:
            return {"error": "Game not found or already complete"}

        # Restore session settings
        self.player_name = data["player1_name"]
        self.ai_difficulty = data["ai_difficulty"] or "medium"
        self.game_mode = data["game_mode"] or "practice"
        self.target_score = data["target_score"]
        self.oklahoma_gin = data["oklahoma_gin"]
        self.spade_doubling = data["spade_doubling"]
        self.match_mode = data["match_mode"]
        self.match_id = data["match_id"]
        self.games_won = {}
        if self.match_mode:
            self.games_won = {
                data["player1_name"]: data["games_won"].get(data["player1_name"], 0),
                data["player2_name"]: data["games_won"].get(data["player2_name"], 0),
            }
        self.match_winner = None
        self.game_over = False
        self.winner = None

        # Create AI
        self.ai = make_ai(DIFFICULTY_TO_AI.get(self.ai_difficulty, "context"))

        # Create Game object
        self.game = Game(
            data["player1_name"],
            data["player2_name"],
            is_oklahoma_gin=self.oklahoma_gin,
            spade_doubling_enabled=self.spade_doubling,
        )
        self.human_idx = 0

        # Restore cumulative scores
        self.game.players[0].score = data["p1_score"]
        self.game.players[1].score = data["p2_score"]

        # Set dealer: alternate from last completed hand's dealer
        last_dealer = data["last_dealer_name"]
        if last_dealer == data["player1_name"]:
            self.game.dealer_idx = 1  # Next dealer is player2
        else:
            self.game.dealer_idx = 0  # Next dealer is player1

        # Deal fresh hand
        self.game.deal()

        # Clean up orphaned incomplete hands (no turns) for this game
        with get_connection() as conn:
            conn.execute(
                """DELETE FROM hands
                   WHERE game_id = ?
                     AND NOT EXISTS (SELECT 1 FROM turns t WHERE t.hand_id = hands.id)""",
                (game_id,),
            )
            conn.commit()

        # Wire up tracker to existing game
        self.tracker = GameTracker()
        self.tracker._game_id = game_id
        self.tracker._hand_number = data["last_hand_number"]
        self.db_game_started = True
        self.buffered_ai_turns = []

        # Start new hand row in DB
        self.tracker.start_hand(self.game.dealer.name)

        # Reset UI state
        self.last_round_result = None
        self.last_ai_action = None
        self.turn_cards_before = None
        self.turn_deadwood_before = None
        self.turn_drew_from = None
        self.turn_card_drawn = None

        return self.get_state()

    def _ai_first_discard(self) -> None:
        """Handle AI's first discard."""
        if self.game is None or self.ai is None:
            return

        discard = self.ai.decide_discard(self.game.current_player.hand)
        self.game.discard_to_start(discard)
        self.last_ai_action = {
            "type": "first_discard",
            "discarded": discard.code,
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
            match_id=self.match_id,
        )
        self.tracker.start_hand(self.pending_dealer_name)

        # Flush any buffered AI turns (including reasoning if captured)
        for turn_data in self.buffered_ai_turns:
            # Pop reasoning before recording turn (not a DB field)
            reasoning = turn_data.pop("_reasoning", None)
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
                decision_type="draw",
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
                decision_type="discard",
                choice=str(reasoning.discard.card),
                reasoning=reasoning.discard.reasoning,
                options_considered=options,
            )

        # Record knock decision
        if reasoning.knock:
            self.tracker.record_ai_decision(
                turn_id=turn_id,
                decision_type="knock",
                choice="knock" if reasoning.knock.should_knock else "no_knock",
                reasoning=reasoning.knock.reasoning,
                options_considered=reasoning.knock.factors,
            )

    def get_state(self) -> dict[str, Any]:
        """Get current game state as JSON-serializable dict."""
        if self.game is None:
            return {"error": "No game in progress"}

        human = self.game.players[self.human_idx]
        opponent = self.game.players[1 - self.human_idx]

        # Analyze hand for melds
        analysis = human.hand.analyze()

        # Build melds list
        melds = []
        for meld in analysis.melds:
            melds.append(
                {
                    "type": "set" if meld.meld_type.name == "SET" else "run",
                    "cards": [c.code for c in meld.cards],
                }
            )

        # Determine phase string
        phase_map = {
            GamePhase.DEALING: "dealing",
            GamePhase.FIRST_DISCARD: "first_discard",
            GamePhase.DRAWING: "drawing",
            GamePhase.DISCARDING: "discarding",
            GamePhase.KNOCKED: "knocked",
            GamePhase.ROUND_OVER: "round_over",
        }
        phase = phase_map.get(self.game.phase, "unknown")

        # Is it human's turn?
        your_turn = self.game.current_player_idx == self.human_idx

        # Handle first discard phase
        if self.game.phase == GamePhase.FIRST_DISCARD and your_turn:
            phase = "discarding"  # Treat as discarding for UI

        # Build message (basic fallback - frontend will handle AI action display)
        if self.game.phase == GamePhase.ROUND_OVER:
            message = "Round over!"
        elif self.game.phase == GamePhase.FIRST_DISCARD:
            if your_turn:
                message = "Discard one card to start the round"
            else:
                message = "Computer is starting..."
        elif your_turn:
            if phase == "drawing":
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
            key=lambda c: (c.suit.value, c.rank.value),
        )

        # Calculate card helpfulness
        helpfulness = calculate_card_helpfulness(
            list(human.hand), context.known_cards.dead_cards if context.known_cards else frozenset()
        )

        state = {
            "phase": phase,
            "your_turn": your_turn,
            "hand": [card_to_dict(c) for c in human.hand],
            "melds": melds,
            "deadwood": analysis.deadwood_value,
            "deadwood_cards": [c.code for c in analysis.deadwood_cards],
            "discard_top": card_to_dict(self.game.top_of_discard) if self.game.top_of_discard else None,
            "deck_remaining": len(self.game.deck),
            "opponent_card_count": len(opponent.hand),
            "scores": {
                human.name: human.score,
                opponent.name: opponent.score,
            },
            "can_knock": self.game.can_knock and your_turn and phase == "discarding",
            "message": message,
            "round_over": self.game.phase == GamePhase.ROUND_OVER,
            "round_result": self._round_result_to_dict() if self.last_round_result else None,
            "ai_action": self.last_ai_action,  # Structured AI action data for frontend
            "assist": {
                "dead_cards": [str(c) for c in dead_cards],  # Use suit symbols
                "opponent_known": [str(c) for c in opponent_known],  # Use suit symbols
                "helpfulness": helpfulness,  # Card helpfulness ranking
            },
            "game_mode": self.game_mode,
            "target_score": self.target_score,
            "game_over": self.game_over,
            "game_winner": self.winner,
            "oklahoma_gin": self.oklahoma_gin,
            "spade_doubling": self.spade_doubling,
            "knock_threshold": self.game.knock_threshold,
            "upcard": card_to_dict(self.game.upcard) if self.game.upcard else None,
            "match_mode": self.match_mode,
            "games_won": self.games_won if self.match_mode else None,
            "match_winner": self.match_winner if self.match_mode else None,
            "player_name": self.player_name,
            "ai_difficulty": self.ai_difficulty,
            "game_id": self.tracker.game_id,
        }

        return state

    def _round_result_to_dict(self) -> dict[str, Any] | None:
        """Convert round result to dict."""
        if not self.last_round_result:
            return None

        def hand_data_to_dict(hd: HandResultData) -> dict:
            return {
                "cards": hd.cards,
                "melds": hd.melds,
                "deadwood": hd.deadwood,
                "deadwood_cards": hd.deadwood_cards,
            }

        return {
            "winner": self.last_round_result.winner,
            "points": self.last_round_result.points,
            "is_gin": self.last_round_result.is_gin,
            "is_undercut": self.last_round_result.is_undercut,
            "is_draw": self.last_round_result.is_draw,
            "player_hand": hand_data_to_dict(self.last_round_result.player_hand),
            "opponent_hand": hand_data_to_dict(self.last_round_result.opponent_hand),
            "layoff_cards": self.last_round_result.layoff_cards,
            "defender_deadwood_before": self.last_round_result.defender_deadwood_before,
        }

    def draw(self, source: str) -> dict[str, Any]:
        """Draw a card from deck or discard."""
        if self.game is None:
            return {"error": "No game in progress"}

        if self.game.current_player_idx != self.human_idx:
            return {"error": "Not your turn"}

        if self.game.phase != GamePhase.DRAWING:
            return {"error": f"Cannot draw in {self.game.phase.name} phase"}

        try:
            human = self.game.players[self.human_idx]

            # Stock exhausted: a deck draw at the minimum ends the round in a draw
            # (mirrors the AI-turn handling; previously this soft-locked the round)
            if source != "discard" and len(self.game.deck) <= self.game.min_deck_cards:
                self._end_round_as_draw()
                return self.get_state()

            # Save turn state BEFORE drawing
            self.turn_cards_before = [c.code for c in human.hand]
            analysis_before = human.hand.analyze()
            self.turn_deadwood_before = analysis_before.deadwood_value

            # Draw the card
            if source == "discard":
                if not self.game.top_of_discard:
                    return {"error": "Discard pile is empty"}
                card = self.game.draw_from_discard()
                self.turn_drew_from = "discard"
            else:
                card = self.game.draw_from_deck()
                self.turn_drew_from = "deck"

            self.turn_card_drawn = card

            return self.get_state()

        except InvalidActionError as e:
            return {"error": str(e)}

    def _end_round_as_draw(self) -> None:
        """End the current round as a draw (stock exhausted)."""
        if self.game is None:
            return

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
        if self.db_game_started:
            self.tracker.end_hand_from_result(self.game.get_draw_result())

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
            return {"error": "No game in progress"}

        if self.game.current_player_idx != self.human_idx:
            return {"error": "Not your turn"}

        try:
            card = Card.parse(card_id)
            human = self.game.players[self.human_idx]

            # Handle first discard phase (no knock possible)
            if self.game.phase == GamePhase.FIRST_DISCARD:
                self.game.discard_to_start(card)
                return self.get_state()

            if self.game.phase != GamePhase.DISCARDING:
                return {"error": f"Cannot discard in {self.game.phase.name} phase"}

            # Rule: cannot discard the card just taken from the discard pile
            if card == self.game.discard_blocked_card:
                return {"error": f"Cannot discard {card} - it was just taken from the discard pile"}

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
                state["needs_knock_decision"] = True
                state["post_discard_deadwood"] = post_discard_deadwood
                state["discard_card"] = card_id
                return state

            # An explicit knock request that isn't legal must fail loudly,
            # not silently downgrade to a plain discard
            if knock and not can_knock_after:
                return {
                    "error": f"Cannot knock: {post_discard_deadwood} deadwood "
                    f"exceeds threshold of {self.game.knock_threshold}"
                }

            if knock and can_knock_after:
                # Ensure DB started before recording turn
                self._ensure_db_started()

                result = self.game.knock_with_discard(card)

                # Record turn with knock
                if (
                    self.turn_cards_before is not None
                    and self.turn_deadwood_before is not None
                    and self.turn_drew_from
                    and self.turn_card_drawn
                ):
                    cards_after = [c.code for c in remaining_cards]
                    self.tracker.record_turn(
                        player_name=human.name,
                        drew_from=self.turn_drew_from,
                        card_drawn=self.turn_card_drawn.code,
                        card_discarded=card.code,
                        did_knock=True,
                        cards_before=self.turn_cards_before,
                        cards_after=cards_after,
                        deadwood_before=self.turn_deadwood_before,
                        deadwood_after=post_discard_deadwood,
                    )

                self._save_round_result(result)
                return self.get_state()

            # Just discard (no knock or can't knock)
            self.game.discard(card)

            # Ensure DB started before recording turn
            self._ensure_db_started()

            # Record turn without knock
            if (
                self.turn_cards_before is not None
                and self.turn_deadwood_before is not None
                and self.turn_drew_from
                and self.turn_card_drawn
            ):
                cards_after = [c.code for c in human.hand]
                deadwood_after = human.hand.analyze().deadwood_value
                self.tracker.record_turn(
                    player_name=human.name,
                    drew_from=self.turn_drew_from,
                    card_drawn=self.turn_card_drawn.code,
                    card_discarded=card.code,
                    did_knock=False,
                    cards_before=self.turn_cards_before,
                    cards_after=cards_after,
                    deadwood_before=self.turn_deadwood_before,
                    deadwood_after=deadwood_after,
                )

            return self.get_state()

        except (InvalidActionError, CardNotInHandError, KeyError, ValueError) as e:
            return {"error": str(e)}

    def knock(self) -> dict[str, Any]:
        """Knock to end the round."""
        if self.game is None:
            return {"error": "No game in progress"}

        if self.game.current_player_idx != self.human_idx:
            return {"error": "Not your turn"}

        if self.game.phase != GamePhase.DISCARDING:
            return {"error": "Can only knock during discard phase"}

        try:
            result = self.game.knock()
            self._save_round_result(result)
            return self.get_state()

        except InvalidActionError as e:
            return {"error": str(e)}

    def ai_turn(self) -> dict[str, Any]:
        """Execute AI's turn."""
        if self.game is None or self.ai is None:
            return {"error": "No game in progress"}

        if self.game.current_player_idx == self.human_idx:
            return {"error": "It's your turn, not AI's"}

        # Handle first discard if needed
        if self.game.phase == GamePhase.FIRST_DISCARD:
            self._ai_first_discard()
            return self.get_state()

        if self.game.phase not in (GamePhase.DRAWING, GamePhase.DISCARDING):
            return {"error": f"Cannot play in {self.game.phase.name} phase"}

        # Save AI player state before turn (for tracking)
        ai_player = self.game.players[1 - self.human_idx]
        cards_before = [c.code for c in ai_player.hand]
        deadwood_before = ai_player.hand.analyze().deadwood_value

        # Execute AI turn with reasoning capture
        turn_result, actions, round_result = execute_ai_turn(self.game, self.ai, capture_reasoning=True)

        # Build AI action first (before checking result type) so it's available for round result modal
        if actions:
            self.last_ai_action = {
                "type": "turn",
                "draw_from": "discard" if actions.draw_source == DrawChoice.DISCARD else "deck",
                "drew_card": actions.drawn_card.code if actions.draw_source == DrawChoice.DISCARD else None,
                "discarded": actions.discarded_card.code,
            }

            # Attach Monte Carlo thinking data if available and enabled
            if isinstance(self.ai, MonteCarloAI) and self.ai.last_mc_thinking:
                from gin_rummy.config import get_config

                if get_config().monte_carlo_ai.show_web_thinking:
                    self.last_ai_action["mc_thinking"] = self.ai.last_mc_thinking
                self.ai.last_mc_thinking = None  # Reset for next turn

            # Prepare turn data for recording
            drew_from = "discard" if actions.draw_source == DrawChoice.DISCARD else "deck"
            if actions.did_knock:
                # Cards after knock (discarded card removed)
                cards_after = [c.code for c in ai_player.hand if c != actions.discarded_card]
            else:
                cards_after = [c.code for c in ai_player.hand]

            turn_data = {
                "player_name": ai_player.name,
                "drew_from": drew_from,
                "card_drawn": actions.drawn_card.code,
                "card_discarded": actions.discarded_card.code,
                "did_knock": actions.did_knock,
                "cards_before": cards_before,
                "cards_after": cards_after,
                "deadwood_before": deadwood_before,
                "deadwood_after": actions.deadwood_after,
            }

            # Buffer AI turn if DB not started, otherwise record directly
            if self.db_game_started:
                turn_id = self.tracker.record_turn(**turn_data)
                # Record AI decisions if reasoning was captured
                if actions.reasoning:
                    self._record_ai_decisions(turn_id, actions.reasoning)
            else:
                # Buffer turn data along with reasoning for later recording
                turn_data["_reasoning"] = actions.reasoning
                self.buffered_ai_turns.append(turn_data)

        if turn_result == TurnResult.DRAW:
            # Deck exhausted
            self._end_round_as_draw()
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
            melds.append(
                {
                    "type": "set" if meld.meld_type.name == "SET" else "run",
                    "cards": [c.code for c in meld.cards],
                }
            )

        return HandResultData(
            cards=[card_to_dict(c) for c in hand],
            melds=melds,
            deadwood=analysis.deadwood_value,
            deadwood_cards=[c.code for c in analysis.deadwood_cards],
        )

    def _save_round_result(self, result: RoundResult) -> None:
        """Save round result for display."""
        if self.game is None:
            return

        winner_name = result.winner.name if result.winner else None

        # Convert layoff cards to string format
        layoff_cards_str = None
        if result.layoff_cards:
            layoff_cards_str = [c.code for c in result.layoff_cards]

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
                        # Game over but match continues - still complete this game in DB
                        self.game_over = True
                        self.winner = game_winner
                        if self.db_game_started:
                            self.tracker.end_game(game_winner, player_score, ai_score)
                else:
                    # Standard mode - game over is final
                    self.game_over = True
                    self.winner = game_winner
                    if self.db_game_started:
                        self.tracker.end_game(game_winner, player_score, ai_score)

        # Record hand result in database only if game was started (human played)
        if self.db_game_started:
            self.tracker.end_hand_from_result(result)

    def new_round(self) -> dict[str, Any]:
        """Start a new round."""
        if self.game is None:
            return {"error": "No game in progress"}

        # Don't start a new round if the game is over
        if self.game_over:
            return self.get_state()

        # Only valid once the current round has actually ended - otherwise a
        # mid-hand request abandons the hand and corrupts DB tracking
        if self.game.phase != GamePhase.ROUND_OVER:
            return {"error": "Cannot start a new round while a round is in progress"}

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
        self.ai = make_ai(DIFFICULTY_TO_AI.get(self.ai_difficulty, "context"))

        self.last_round_result = None
        self.last_ai_action = None

        # Reset turn tracking state
        self.turn_cards_before = None
        self.turn_deadwood_before = None
        self.turn_drew_from = None
        self.turn_card_drawn = None

        return self.get_state()
