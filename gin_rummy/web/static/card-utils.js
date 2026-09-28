/**
 * Shared card display constants and helpers.
 *
 * Single source of truth for suit symbols/colors across all pages
 * (game.js, replay.js, memory.js, scenario.js). Load this script
 * before any script that uses window.CardUtils.
 *
 * Two key formats exist in the codebase:
 * - Suit letters ('S','H','D','C') from card IDs like "7H", "10S"
 * - Suit names ('spades',...) from card dicts sent by the server
 */

window.CardUtils = (function () {
    const SUIT_SYMBOLS_BY_LETTER = { S: '♠', H: '♥', D: '♦', C: '♣' };

    const SUIT_SYMBOLS_BY_NAME = {
        spades: '♠',
        hearts: '♥',
        diamonds: '♦',
        clubs: '♣',
    };

    const RED_SUIT_LETTERS = new Set(['H', 'D']);
    const RED_SUIT_NAMES = new Set(['hearts', 'diamonds']);

    /** Format a card ID (e.g. "7H") as display text (e.g. "7♥"). */
    function formatCardId(cardId) {
        if (!cardId) return '';
        const suit = cardId.slice(-1);
        const rank = cardId.slice(0, -1);
        return `${rank}${SUIT_SYMBOLS_BY_LETTER[suit] || suit}`;
    }

    /** True if a card ID belongs to a red suit. */
    function isRedId(cardId) {
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
    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);
    }

    return {
        SUIT_SYMBOLS_BY_LETTER,
        SUIT_SYMBOLS_BY_NAME,
        RED_SUIT_LETTERS,
        RED_SUIT_NAMES,
        formatCardId,
        isRedId,
        escapeHtml,
    };
})();
