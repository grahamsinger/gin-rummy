"""Tests for game module."""

import pytest
from gin_rummy.game import Game, GamePhase, InvalidActionError, RoundResult
from gin_rummy.card import Card, Suit, Rank


class TestGameSetup:
    def test_create_game(self):
        game = Game("Alice", "Bob")
        assert game.players[0].name == "Alice"
        assert game.players[1].name == "Bob"
        assert game.phase == GamePhase.DEALING

    def test_initial_state(self):
        game = Game("Alice", "Bob")
        assert len(game.deck) == 52
        assert len(game.discard_pile) == 0
        assert game.dealer_idx == 0


class TestDealing:
    def test_deal_cards(self):
        game = Game("Alice", "Bob")
        game.deal()

        # Each player should have 10 cards, non-dealer has 11
        dealer = game.dealer
        non_dealer = game.non_dealer
        assert len(dealer.hand) == 10
        assert len(non_dealer.hand) == 11

    def test_deal_sets_phase(self):
        game = Game("Alice", "Bob")
        game.deal()
        assert game.phase == GamePhase.FIRST_DISCARD

    def test_deal_non_dealer_is_current(self):
        game = Game("Alice", "Bob")
        game.deal()
        assert game.current_player == game.non_dealer

    def test_deal_reduces_deck(self):
        game = Game("Alice", "Bob")
        game.deal()
        # 52 - 10 - 10 - 1 = 31
        assert len(game.deck) == 31

    def test_cannot_deal_twice(self):
        game = Game("Alice", "Bob")
        game.deal()
        with pytest.raises(InvalidActionError):
            game.deal()


class TestFirstDiscard:
    def test_discard_to_start(self):
        game = Game("Alice", "Bob")
        game.deal()
        card = game.current_player.hand[0]
        game.discard_to_start(card)

        assert game.phase == GamePhase.DRAWING
        assert len(game.current_player.hand) == 10
        assert game.top_of_discard == card

    def test_cannot_discard_card_not_in_hand(self):
        game = Game("Alice", "Bob")
        game.deal()
        # Find a card not in non-dealer's hand
        hand_cards = set(game.current_player.hand)
        all_cards = [Card(rank, suit) for suit in Suit for rank in Rank]
        fake_card = next(c for c in all_cards if c not in hand_cards)

        with pytest.raises(InvalidActionError):
            game.discard_to_start(fake_card)


class TestDrawing:
    def setup_drawing_phase(self) -> Game:
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        return game

    def test_draw_from_deck(self):
        game = self.setup_drawing_phase()
        initial_hand_size = len(game.current_player.hand)
        initial_deck_size = len(game.deck)

        card = game.draw_from_deck()

        assert len(game.current_player.hand) == initial_hand_size + 1
        assert len(game.deck) == initial_deck_size - 1
        assert card in game.current_player.hand

    def test_draw_from_deck_sets_phase(self):
        game = self.setup_drawing_phase()
        game.draw_from_deck()
        assert game.phase == GamePhase.DISCARDING

    def test_draw_from_discard(self):
        game = self.setup_drawing_phase()
        top_card = game.top_of_discard
        initial_hand_size = len(game.current_player.hand)

        card = game.draw_from_discard()

        assert card == top_card
        assert len(game.current_player.hand) == initial_hand_size + 1
        assert card in game.current_player.hand
        assert len(game.discard_pile) == 0

    def test_cannot_draw_when_not_drawing_phase(self):
        game = Game("Alice", "Bob")
        game.deal()
        # In FIRST_DISCARD phase
        with pytest.raises(InvalidActionError):
            game.draw_from_deck()


class TestDiscarding:
    def setup_discarding_phase(self) -> Game:
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        game.draw_from_deck()
        return game

    def test_discard(self):
        game = self.setup_discarding_phase()
        current = game.current_player
        card = current.hand[0]

        game.discard(card)

        assert card not in current.hand
        assert game.top_of_discard == card

    def test_discard_switches_turn(self):
        game = self.setup_discarding_phase()
        current = game.current_player
        game.discard(current.hand[0])

        assert game.current_player != current
        assert game.phase == GamePhase.DRAWING

    def test_cannot_discard_card_not_in_hand(self):
        game = self.setup_discarding_phase()
        hand_cards = set(game.current_player.hand)
        all_cards = [Card(rank, suit) for suit in Suit for rank in Rank]
        fake_card = next(c for c in all_cards if c not in hand_cards)

        with pytest.raises(InvalidActionError):
            game.discard(fake_card)


class TestKnocking:
    def test_can_knock_with_low_deadwood(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        game.draw_from_deck()

        # Force low deadwood by replacing hand
        game.current_player.hand._cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.ACE, Suit.CLUBS),
            Card(Rank.ACE, Suit.DIAMONDS),
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.TWO, Suit.DIAMONDS),
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.THREE, Suit.HEARTS),
        ]  # Total: 4*1 + 4*2 + 2*3 = 18, still too high

        # Actually let's make it 10 or less
        game.current_player.hand._cards = [
            Card(Rank.ACE, Suit.SPADES),   # 1
            Card(Rank.ACE, Suit.HEARTS),   # 1
            Card(Rank.ACE, Suit.CLUBS),    # 1
            Card(Rank.ACE, Suit.DIAMONDS), # 1
            Card(Rank.TWO, Suit.SPADES),   # 2
            Card(Rank.TWO, Suit.HEARTS),   # 2
            Card(Rank.TWO, Suit.CLUBS),    # 2
        ]  # Total: 10

        assert game.can_knock

    def test_cannot_knock_with_high_deadwood(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        game.draw_from_deck()

        # Force high deadwood
        game.current_player.hand._cards = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.QUEEN, Suit.HEARTS),
        ]  # Total: 20

        assert not game.can_knock

    def test_knock_returns_result(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        game.draw_from_deck()

        # Setup knocker with 5 deadwood
        game.current_player.hand._cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
            Card(Rank.THREE, Suit.CLUBS),
        ]

        # Setup defender with 15 deadwood
        game.opponent.hand._cards = [
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.TEN, Suit.HEARTS),
        ]

        result = game.knock()

        assert isinstance(result, RoundResult)
        assert result.winner == game.players[game.current_player_idx]  # knocker
        assert result.points == 10  # 15 - 5


class TestGinAndUndercut:
    def test_gin_bonus(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        game.draw_from_deck()

        knocker = game.current_player
        defender = game.opponent

        # Gin: 0 deadwood (empty hand for test)
        knocker.hand._cards = []

        # Defender has 20 deadwood
        defender.hand._cards = [
            Card(Rank.TEN, Suit.SPADES),
            Card(Rank.TEN, Suit.HEARTS),
        ]

        result = game.knock()

        assert result.is_gin
        assert result.winner == knocker
        assert result.points == 25 + 20  # bonus + defender deadwood

    def test_undercut(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        game.draw_from_deck()

        knocker = game.current_player
        defender = game.opponent

        # Knocker has 8 deadwood
        knocker.hand._cards = [
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.FIVE, Suit.HEARTS),
        ]

        # Defender has 5 deadwood (less than knocker)
        defender.hand._cards = [
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.THREE, Suit.HEARTS),
        ]

        result = game.knock()

        assert result.is_undercut
        assert result.winner == defender
        assert result.points == 25 + (8 - 5)  # bonus + difference


class TestNewRound:
    def test_new_round_alternates_dealer(self):
        game = Game("Alice", "Bob")
        assert game.dealer_idx == 0

        game.new_round()
        assert game.dealer_idx == 1

        game.new_round()
        assert game.dealer_idx == 0

    def test_new_round_resets_phase(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.new_round()
        assert game.phase == GamePhase.DEALING


class TestProperties:
    def test_top_of_discard_empty(self):
        game = Game("Alice", "Bob")
        assert game.top_of_discard is None

    def test_current_player_and_opponent(self):
        game = Game("Alice", "Bob")
        game.deal()

        current = game.current_player
        opp = game.opponent

        assert current != opp
        assert current in game.players
        assert opp in game.players


class TestAssistTracking:
    """Tests for assist mode card tracking features."""

    def test_discard_history_tracks_first_discard(self):
        game = Game("Alice", "Bob")
        game.deal()
        card = game.current_player.hand[0]
        game.discard_to_start(card)

        assert card in game.discard_history
        assert len(game.discard_history) == 1

    def test_discard_history_tracks_regular_discards(self):
        game = Game("Alice", "Bob")
        game.deal()
        first_card = game.current_player.hand[0]
        game.discard_to_start(first_card)

        game.draw_from_deck()
        second_card = game.current_player.hand[0]
        game.discard(second_card)

        assert first_card in game.discard_history
        assert second_card in game.discard_history
        assert len(game.discard_history) == 2

    def test_discard_history_resets_on_new_deal(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])

        assert len(game.discard_history) == 1

        game.new_round()
        game.deal()

        assert len(game.discard_history) == 0

    def test_player_pickups_empty_initially(self):
        game = Game("Alice", "Bob")
        game.deal()

        assert len(game.get_player_pickups("Alice")) == 0
        assert len(game.get_player_pickups("Bob")) == 0

    def test_player_pickups_tracks_discard_draw(self):
        game = Game("Alice", "Bob")
        game.deal()
        discard_card = game.current_player.hand[0]
        game.discard_to_start(discard_card)

        # Now dealer draws from discard
        current_name = game.current_player.name
        picked_up = game.draw_from_discard()

        assert picked_up == discard_card
        assert picked_up in game.get_player_pickups(current_name)
        assert len(game.get_player_pickups(current_name)) == 1

    def test_player_pickups_resets_on_new_deal(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])
        game.draw_from_discard()

        current_name = game.current_player.name
        assert len(game.get_player_pickups(current_name)) == 1

        game.new_round()
        game.deal()

        assert len(game.get_player_pickups(current_name)) == 0

    def test_deck_draw_not_tracked_as_pickup(self):
        game = Game("Alice", "Bob")
        game.deal()
        game.discard_to_start(game.current_player.hand[0])

        current_name = game.current_player.name
        game.draw_from_deck()

        assert len(game.get_player_pickups(current_name)) == 0
