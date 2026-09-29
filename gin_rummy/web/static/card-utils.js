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
