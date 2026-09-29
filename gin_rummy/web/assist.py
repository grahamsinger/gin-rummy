"""Assist mode: how much each card not in hand would help."""

from __future__ import annotations

from typing import Any

from gin_rummy.models import Card, Rank, Suit, analyze_hand


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
