// Mutable UI state shared by the game modules (the `ui` object), plus the settings remembered in localStorage.

// Reassigned across modules, so it lives on one object (ES module bindings are read-only)
export const ui = {
    gameState: null,
    pendingDiscardCard: null,
    pendingMeldDiscardCard: null,
    sortMode: localStorage.getItem('sortMode') || 'value',
    drawnCardId: null,
    currentViewedPlayer: null,
    handReplay: null,
};

// Store player names for replay
export let scoreHistoryPlayerNames = { player1: '', player2: '' };

// Settings persistence
export const savedSettings = {
    playerName: localStorage.getItem('playerName') || null,
    aiDifficulty: localStorage.getItem('aiDifficulty') || 'medium'
};

// Generate a random player name like "Guest_a3f7"
export function generatePlayerName() {
    const suffix = Math.random().toString(16).substring(2, 6);
    return `Guest_${suffix}`;
}
