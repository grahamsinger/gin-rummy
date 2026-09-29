/**
 * Shared card display constants and helpers.
 *
 * Single source of truth for suit symbols/colors across all pages
 * (game.js, replay.js, memory.js, scenario.js).
 *
 * Two key formats exist in the codebase:
 * - Suit letters ('S','H','D','C') from card IDs like "7H", "10S"
 * - Suit names ('spades',...) from card dicts sent by the server
 */

export const SUIT_SYMBOLS_BY_LETTER = { S: '♠', H: '♥', D: '♦', C: '♣' };

export const SUIT_SYMBOLS_BY_NAME = {
    spades: '♠',
    hearts: '♥',
    diamonds: '♦',
    clubs: '♣',
};

export const RED_SUIT_LETTERS = new Set(['H', 'D']);
export const RED_SUIT_NAMES = new Set(['hearts', 'diamonds']);

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

/** Sort card dicts by a sort mode: 'suit', 'rank' (run-aware) or 'value'. */
export function sortCards(cards, mode) {
    const sorted = [...cards];

    if (mode === 'suit') {
        // Sort by suit first, then by rank within suit
        sorted.sort((a, b) => {
            const suitDiff = SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
            if (suitDiff !== 0) return suitDiff;
            return RANK_ORDER[a.rank] - RANK_ORDER[b.rank];
        });
    } else if (mode === 'rank') {
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
    } else if (mode === 'value') {
        // Sort by deadwood value (highest first), then by suit
        sorted.sort((a, b) => {
            const valueDiff = getCardValue(b) - getCardValue(a);
            if (valueDiff !== 0) return valueDiff;
            return SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
        });
    }

    return sorted;
}

/** Format a card ID (e.g. "7H") as display text (e.g. "7♥"). */
export function formatCardId(cardId) {
    if (!cardId) return '';
    const suit = cardId.slice(-1);
    const rank = cardId.slice(0, -1);
    return `${rank}${SUIT_SYMBOLS_BY_LETTER[suit] || suit}`;
}

/** True if a card ID belongs to a red suit. */
export function isRedId(cardId) {
    return !!cardId && RED_SUIT_LETTERS.has(cardId.slice(-1));
}

const HTML_ESCAPES = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
};

/**
 * Escape a value for safe interpolation into innerHTML, in both text
 * and attribute contexts. Use this for anything user-controlled
 * (player names from the DB, etc.).
 */
export function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);
}
