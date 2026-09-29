// Card ordering, sorting and the card element itself.
import { RANK_ORDER, SUIT_SYMBOLS_BY_NAME, sortCards as sortCardsBy } from '../card-utils.js';
import { ui } from './state.js';

export { RANK_ORDER };

// Suit symbols - shared definitions from card-utils.js
export const SUIT_SYMBOLS = SUIT_SYMBOLS_BY_NAME;

// Sort cards based on current sort mode
export function sortCards(cards) {
    return sortCardsBy(cards, ui.sortMode);
}

// Create a card element
export function createCardElement(card, faceDown = false) {
    const div = document.createElement('div');

    if (faceDown) {
        div.className = 'card card-back';
        return div;
    }

    if (!card) {
        div.className = 'card empty';
        return div;
    }

    div.className = `card ${card.suit}`;
    div.dataset.cardId = card.id;

    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = card.rank;

    const suit = document.createElement('span');
    suit.className = 'suit';
    suit.textContent = SUIT_SYMBOLS[card.suit];

    div.appendChild(rank);
    div.appendChild(suit);

    return div;
}

// Format card ID (e.g., "KD") to display format (e.g., "K♦")
// Also handles cards already in symbol format (e.g., "K♦", "10♥")
export function formatCardId(cardId) {
    if (!cardId) return cardId;
    // Already has suit symbol - return as-is
    if (/[♠♥♦♣]$/.test(cardId)) return cardId;
    const suitChar = cardId.slice(-1);
    const rank = cardId.slice(0, -1);
    const suitMap = { 'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣' };
    return rank + (suitMap[suitChar] || suitChar);
}

// Check if a card is part of a meld
export function isCardInMeld(cardId) {
    if (!ui.gameState || !ui.gameState.melds) {
        return false;
    }
    return ui.gameState.melds.some(meld => meld.cards.includes(cardId));
}
