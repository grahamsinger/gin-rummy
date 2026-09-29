// Card ordering, sorting and the card element itself.
import { SUIT_SYMBOLS_BY_NAME } from '../card-utils.js';
import { ui } from './state.js';

// Suit symbols - shared definitions from card-utils.js
export const SUIT_SYMBOLS = SUIT_SYMBOLS_BY_NAME;

// Suit order for sorting
const SUIT_ORDER = {
    spades: 0,
    hearts: 1,
    diamonds: 2,
    clubs: 3,
};

// Rank order for sorting
export const RANK_ORDER = {
    'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13,
};

// Card deadwood value
function getCardValue(card) {
    if (card.rank === 'A') return 1;
    if (['J', 'Q', 'K'].includes(card.rank)) return 10;
    return parseInt(card.rank);
}

// Sort cards based on current sort mode
export function sortCards(cards) {
    const sorted = [...cards];

    if (ui.sortMode === 'suit') {
        // Sort by suit first, then by rank within suit
        sorted.sort((a, b) => {
            const suitDiff = SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
            if (suitDiff !== 0) return suitDiff;
            return RANK_ORDER[a.rank] - RANK_ORDER[b.rank];
        });
    } else if (ui.sortMode === 'rank') {
        // Run-aware sorting: keep consecutive same-suit cards together
        // Group cards by rank
        const rankGroups = {};
        cards.forEach(card => {
            const rank = RANK_ORDER[card.rank];
            if (!rankGroups[rank]) rankGroups[rank] = [];
            rankGroups[rank].push(card);
        });

        // Build a map of suit -> ranks for looking ahead
        const suitRanks = {};
        cards.forEach(card => {
            const suit = card.suit;
            if (!suitRanks[suit]) suitRanks[suit] = new Set();
            suitRanks[suit].add(RANK_ORDER[card.rank]);
        });

        // Process ranks in order, placing cards to keep sequences together
        const sortedRanks = Object.keys(rankGroups).map(Number).sort((a, b) => a - b);
        const result = [];
        const placedSuits = new Map(); // Track last rank placed for each suit

        sortedRanks.forEach(rank => {
            const cardsInRank = rankGroups[rank];

            // Sort cards to keep same-suit sequences together
            cardsInRank.sort((a, b) => {
                const aExtendsBackward = placedSuits.has(a.suit) && placedSuits.get(a.suit) === rank - 1;
                const bExtendsBackward = placedSuits.has(b.suit) && placedSuits.get(b.suit) === rank - 1;
                const aExtendsForward = suitRanks[a.suit]?.has(rank + 1);
                const bExtendsForward = suitRanks[b.suit]?.has(rank + 1);

                // Priority 1: Cards that extend existing sequences (backward) come first
                if (aExtendsBackward && !bExtendsBackward) return -1;
                if (!aExtendsBackward && bExtendsBackward) return 1;

                // Priority 2: Cards that will continue into future sequences come last (next to their continuations)
                if (aExtendsForward && !bExtendsForward) return 1;
                if (!aExtendsForward && bExtendsForward) return -1;

                // Priority 3: If tied, use suit order
                return SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
            });

            // Add cards and update tracking
            cardsInRank.forEach(card => {
                result.push(card);
                placedSuits.set(card.suit, rank);
            });
        });

        return result;
    } else if (ui.sortMode === 'value') {
        // Sort by deadwood value (highest first), then by suit
        sorted.sort((a, b) => {
            const valueDiff = getCardValue(b) - getCardValue(a);
            if (valueDiff !== 0) return valueDiff;
            return SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
        });
    }

    return sorted;
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
