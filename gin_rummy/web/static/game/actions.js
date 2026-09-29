// Game flow: new game, draw, discard, AI turn, next round, resume, sort mode.
import { displayAiAction, renderMcThinking } from './ai-playback.js';
import { API_BASE, apiCall } from './api.js';
import { renderGameState } from './board.js';
import { elements } from './dom.js';
import { showGameOver, showResumePrompt } from './modals.js';
import { ui, generatePlayerName, savedSettings } from './state.js';

export async function newGame(settings = null) {
    elements.roundModal.classList.add('hidden');
    elements.settingsModal.classList.add('hidden');
    elements.lastAiMove.textContent = '';  // Clear last AI move
    renderMcThinking(null);  // Clear thinking panel
    elements.knockCheckbox.checked = false;  // Reset knock checkbox
    const state = await apiCall('/new', 'POST', settings);
    if (state) {
        renderGameState(state);

        // Check if AI goes first (e.g., in Oklahoma mode when computer is non-dealer)
        if (!state.your_turn) {
            await doAiTurn();
        }
    }
}

export async function drawCard(source) {
    // Store hand before drawing to find the new card
    const handBefore = ui.gameState ? ui.gameState.hand.map(c => c.id) : [];

    const state = await apiCall('/draw', 'POST', { source });
    if (state) {
        // Find which card was drawn by comparing hands
        if (source === 'discard' && ui.gameState && ui.gameState.discard_top) {
            // If drawing from discard, we know which card it is
            ui.drawnCardId = ui.gameState.discard_top.id;
        } else {
            // If drawing from deck, find the new card
            const handAfter = state.hand.map(c => c.id);
            const newCards = handAfter.filter(id => !handBefore.includes(id));
            if (newCards.length > 0) {
                ui.drawnCardId = newCards[0];
            }
        }

        renderGameState(state);

        // If it's still our turn (discarding phase), wait for discard
        // If it's AI's turn, trigger AI turn
        if (!state.your_turn) {
            await doAiTurn();
        }
    }
}

export async function discardCard(cardId, knock = null) {
    // If knock not explicitly set, only use checkbox if it's checked
    // Otherwise pass null to let backend handle automatic gin detection
    if (knock === null) {
        knock = elements.knockCheckbox.checked ? true : null;
    }

    const state = await apiCall('/discard', 'POST', { card: cardId, knock: knock });
    if (state) {
        // Check if we need to ask about knocking (for gin auto-knock)
        if (state.needs_knock_decision) {
            // If gin (0 deadwood), automatically knock without confirmation
            if (state.post_discard_deadwood === 0) {
                await discardCard(state.discard_card, true);
                return;
            }

            // This shouldn't happen with the checkbox approach, but handle it anyway
            // by treating it as a regular discard
            knock = false;
            await discardCard(state.discard_card, knock);
            return;
        }

        // Clear drawn card highlight after discard
        ui.drawnCardId = null;

        // Uncheck the knock checkbox after use
        elements.knockCheckbox.checked = false;

        renderGameState(state);

        // After discarding, it's AI's turn
        if (!state.your_turn && !state.round_over) {
            await doAiTurn();
        }
    }
}

export async function nextRound() {
    elements.roundModal.classList.add('hidden');

    // Check if game is over before starting new round
    if (ui.gameState && ui.gameState.game_over && ui.gameState.game_winner) {
        showGameOver(ui.gameState.game_winner, ui.gameState.scores, ui.gameState.target_score, ui.gameState.match_mode, ui.gameState.games_won, ui.gameState.match_winner);
        return;
    }

    elements.lastAiMove.textContent = '';  // Clear last AI move
    renderMcThinking(null);  // Clear thinking panel
    elements.knockCheckbox.checked = false;  // Reset knock checkbox
    const state = await apiCall('/new-round', 'POST');
    if (state) {
        renderGameState(state);

        // Check if AI goes first
        if (!state.your_turn) {
            await doAiTurn();
        }
    }
}

export async function doAiTurn() {
    // Show thinking indicator
    elements.lastAiMove.textContent = "Computer is thinking...";
    elements.lastAiMove.classList.add('thinking');

    // Run API call with a minimum visible delay so the thinking state is apparent
    const [state] = await Promise.all([
        apiCall('/ai-turn', 'POST'),
        new Promise(resolve => setTimeout(resolve, 600)),
    ]);
    if (state) {
        // Display AI actions sequentially if available
        if (state.ai_action) {
            await displayAiAction(state.ai_action, state);
        } else {
            renderGameState(state);
        }

        // If still AI's turn (shouldn't happen normally), continue
        if (!state.your_turn && !state.round_over) {
            await doAiTurn();
        }
    }
}

// Try to restore an existing game session, or start a new game
export async function restoreOrStartGame() {
    let sessionState = null;

    try {
        // Check if there's an existing game in progress (session cookie)
        const response = await fetch(`${API_BASE}/state`);
        const state = await response.json();

        if (state && !state.error && state.hand && state.hand.length > 0) {
            sessionState = state;
        }
    } catch (e) {
        console.log('Error checking for existing game:', e);
    }

    // Check for resumable games in the database
    const playerName = savedSettings.playerName;
    if (playerName) {
        try {
            const response = await fetch(`/api/games/resumable?player_name=${encodeURIComponent(playerName)}`);
            const data = await response.json();
            if (data.games && data.games.length > 0) {
                const resumableGame = data.games[0]; // Most recent
                const sessionGameId = sessionState ? sessionState.game_id : null;

                // Show modal if the most recent resumable game differs from the session game
                if (resumableGame.game_id !== sessionGameId) {
                    elements.settingsModal.classList.add('hidden');
                    showResumePrompt(data.games);
                    return;
                }
            }
        } catch (e) {
            console.log('Error checking for resumable games:', e);
        }
    }

    // If session has a valid game, restore it
    if (sessionState) {
        console.log('Restoring existing game session');
        elements.settingsModal.classList.add('hidden');
        renderGameState(sessionState);

        // If it's the computer's turn (e.g. page refreshed mid-AI-turn),
        // kick the AI - nothing else will, and the game would hang
        if (!sessionState.your_turn && !sessionState.round_over) {
            await doAiTurn();
        }
        return;
    }

    // No existing or resumable game - start a new one
    startNewGameWithSavedSettings();
}

// Start a new game using saved localStorage settings
export function startNewGameWithSavedSettings() {
    console.log('Starting new game with saved settings');

    // Generate player name if none saved
    if (!savedSettings.playerName) {
        savedSettings.playerName = generatePlayerName();
        localStorage.setItem('playerName', savedSettings.playerName);
    }

    const gameMode = localStorage.getItem('gameMode') || 'target';
    const targetScore = localStorage.getItem('targetScore') || '100';
    const oklahomaGin = localStorage.getItem('oklahomaGin') === 'true';
    const spadeDoubling = localStorage.getItem('spadeDoubling') !== 'false';
    const matchMode = localStorage.getItem('matchMode') === 'true';

    const settings = {
        player_name: savedSettings.playerName,
        ai_difficulty: savedSettings.aiDifficulty,
        game_mode: gameMode,
        target_score: gameMode === 'target' ? parseInt(targetScore) : null,
        oklahoma_gin: oklahomaGin,
        spade_doubling: spadeDoubling,
        match_mode: matchMode,
    };
    newGame(settings);
}

// Set sort mode and re-render
export function setSortMode(mode) {
    ui.sortMode = mode;
    localStorage.setItem('sortMode', mode);
    updateSortButtonStates();
    if (ui.gameState) {
        renderGameState(ui.gameState);
    }
}

// Update active state of sort buttons
export function updateSortButtonStates() {
    elements.sortSuitBtn.classList.toggle('active', ui.sortMode === 'suit');
    elements.sortRankBtn.classList.toggle('active', ui.sortMode === 'rank');
    elements.sortValueBtn.classList.toggle('active', ui.sortMode === 'value');
}
