// Entry point: wires the controls and starts or restores a game.
import { discardCard, doAiTurn, drawCard, newGame, nextRound, restoreOrStartGame, setSortMode, startNewGameWithSavedSettings, updateSortButtonStates } from './actions.js';
import { renderGameState } from './board.js';
import { elements } from './dom.js';
import { showScoreHistory } from './score-history.js';
import { loadPlayerNamesForSettings, showSettingsModal } from './settings.js';
import { ui, generatePlayerName, savedSettings } from './state.js';
import { confirmClearStats, loadSelectedPlayerStats, showClearStatsConfirmation, showPlayerStats } from './stats.js';

// Initialize event listeners
function init() {
    // Deck click
    elements.deck.addEventListener('click', () => {
        if (ui.gameState && ui.gameState.your_turn && ui.gameState.phase === 'drawing') {
            drawCard('deck');
        }
    });

    // Discard pile click
    elements.discardPile.addEventListener('click', () => {
        if (ui.gameState && ui.gameState.your_turn && ui.gameState.phase === 'drawing' && ui.gameState.discard_top) {
            drawCard('discard');
        }
    });

    // Knock modal - Yes button
    elements.knockYesBtn.addEventListener('click', async () => {
        elements.knockModal.classList.add('hidden');
        if (ui.pendingDiscardCard) {
            await discardCard(ui.pendingDiscardCard, true);
            ui.pendingDiscardCard = null;
        }
    });

    // Knock modal - No button
    elements.knockNoBtn.addEventListener('click', async () => {
        elements.knockModal.classList.add('hidden');
        if (ui.pendingDiscardCard) {
            await discardCard(ui.pendingDiscardCard, false);
            ui.pendingDiscardCard = null;
        }
    });

    // Resume modal buttons
    elements.resumeYesBtn.addEventListener('click', async () => {
        const gameId = parseInt(elements.resumeYesBtn.dataset.gameId, 10);
        elements.resumeModal.classList.add('hidden');
        try {
            const response = await fetch('/api/game/resume', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId }),
            });
            const state = await response.json();
            if (state && !state.error) {
                renderGameState(state);
                if (!state.your_turn) {
                    await doAiTurn();
                }
            }
        } catch (e) {
            console.error('Failed to resume game:', e);
            startNewGameWithSavedSettings();
        }
    });
    elements.resumeNoBtn.addEventListener('click', () => {
        elements.resumeModal.classList.add('hidden');
        showSettingsModal();
    });
    elements.resumeModal.addEventListener('click', (e) => {
        if (e.target === elements.resumeModal) {
            elements.resumeModal.classList.add('hidden');
            showSettingsModal();
        }
    });

    // Settings modal cancel button and backdrop click
    elements.cancelSettingsBtn.addEventListener('click', () => {
        elements.settingsModal.classList.add('hidden');
    });
    elements.settingsModal.addEventListener('click', (e) => {
        if (e.target === elements.settingsModal) {
            elements.settingsModal.classList.add('hidden');
        }
    });

    // Game mode change handler - show/hide target score
    elements.gameModeSelect.addEventListener('change', () => {
        if (elements.gameModeSelect.value === 'target') {
            elements.targetScoreField.style.display = 'flex';
        } else {
            elements.targetScoreField.style.display = 'none';
        }
    });

    // Oklahoma Gin toggle handler - show/hide spade doubling
    elements.oklahomaGinCheckbox.addEventListener('change', (e) => {
        elements.spadeDoublingField.style.display = e.target.checked ? 'flex' : 'none';
    });

    // Settings form submission
    elements.settingsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        let playerName = elements.playerNameInput.value.trim() || savedSettings.playerName || generatePlayerName();

        // Prevent using "Computer" as player name
        if (playerName.toLowerCase() === 'computer') {
            alert('You cannot use "Computer" as your name - that\'s reserved for the AI!');
            return;
        }

        const aiDifficulty = elements.aiDifficultySelect.value;
        const gameMode = elements.gameModeSelect.value;
        const targetScore = gameMode === 'target' ? parseInt(elements.targetScoreSelect.value) : null;
        const oklahomaGin = elements.oklahomaGinCheckbox.checked;
        const spadeDoubling = elements.spadeDoublingCheckbox.checked;
        const matchMode = elements.matchModeCheckbox.checked;

        // Save to localStorage (always save - either user-provided or generated)
        localStorage.setItem('playerName', playerName);
        localStorage.setItem('aiDifficulty', aiDifficulty);
        localStorage.setItem('gameMode', gameMode);
        if (targetScore) {
            localStorage.setItem('targetScore', targetScore.toString());
        }
        localStorage.setItem('oklahomaGin', oklahomaGin);
        localStorage.setItem('spadeDoubling', spadeDoubling);
        localStorage.setItem('matchMode', matchMode);

        // Update savedSettings (playerName is always set now)
        savedSettings.playerName = playerName;
        savedSettings.aiDifficulty = aiDifficulty;

        const settings = {
            player_name: playerName,
            ai_difficulty: aiDifficulty,
            game_mode: gameMode,
            target_score: targetScore,
            oklahoma_gin: oklahomaGin,
            spade_doubling: spadeDoubling,
            match_mode: matchMode,
        };
        newGame(settings);
    });

    // New game button
    elements.newGameBtn.addEventListener('click', showSettingsModal);

    // Next round button
    elements.nextRoundBtn.addEventListener('click', nextRound);

    // Game over modal buttons
    elements.newGameAfterWinBtn.addEventListener('click', async () => {
        elements.gameOverModal.classList.add('hidden');
        // Start new game immediately with saved settings (Play Again)
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
        await newGame(settings);
    });
    elements.viewStatsAfterWinBtn.addEventListener('click', () => {
        elements.gameOverModal.classList.add('hidden');
        showPlayerStats();
    });
    elements.changeSettingsAfterWinBtn.addEventListener('click', () => {
        elements.gameOverModal.classList.add('hidden');
        showSettingsModal();
    });

    // Assist mode toggle
    elements.assistMode.addEventListener('change', () => {
        if (ui.gameState) {
            renderGameState(ui.gameState);
        }
    });

    // Meld confirmation modal - Yes button
    elements.meldConfirmYesBtn.addEventListener('click', async () => {
        elements.meldConfirmModal.classList.add('hidden');
        if (ui.pendingMeldDiscardCard) {
            await discardCard(ui.pendingMeldDiscardCard);
            ui.pendingMeldDiscardCard = null;
        }
    });

    // Meld confirmation modal - No button
    elements.meldConfirmNoBtn.addEventListener('click', () => {
        elements.meldConfirmModal.classList.add('hidden');
        ui.pendingMeldDiscardCard = null;
        // User can now click another card
    });

    // Sort buttons
    elements.sortSuitBtn.addEventListener('click', () => setSortMode('suit'));
    elements.sortRankBtn.addEventListener('click', () => setSortMode('rank'));
    elements.sortValueBtn.addEventListener('click', () => setSortMode('value'));

    // Stats button and modal
    elements.viewStatsBtn.addEventListener('click', showPlayerStats);
    elements.statsCloseBtn.addEventListener('click', () => {
        elements.statsModal.classList.add('hidden');
    });
    elements.statsModal.addEventListener('click', (e) => {
        if (e.target === elements.statsModal) {
            elements.statsModal.classList.add('hidden');
        }
    });

    // Player selection - auto-load on change
    elements.statsPlayerSelect.addEventListener('change', loadSelectedPlayerStats);

    // Clear stats
    elements.clearStatsBtn.addEventListener('click', showClearStatsConfirmation);
    elements.clearStatsConfirmBtn.addEventListener('click', confirmClearStats);
    elements.clearStatsCancelBtn.addEventListener('click', () => {
        elements.clearStatsModal.classList.add('hidden');
    });

    // Score History button and modal
    elements.scoreHistoryBtn.addEventListener('click', showScoreHistory);
    elements.scoreHistoryCloseBtn.addEventListener('click', () => {
        elements.scoreHistoryModal.classList.add('hidden');
    });
    elements.scoreHistoryModal.addEventListener('click', (e) => {
        if (e.target === elements.scoreHistoryModal) {
            elements.scoreHistoryModal.classList.add('hidden');
        }
    });

    // Mini Games modal
    elements.miniGamesBtn.addEventListener('click', () => {
        elements.miniGamesModal.classList.remove('hidden');
    });
    elements.miniGamesCloseBtn.addEventListener('click', () => {
        elements.miniGamesModal.classList.add('hidden');
    });
    elements.miniGamesModal.addEventListener('click', (e) => {
        if (e.target === elements.miniGamesModal) {
            elements.miniGamesModal.classList.add('hidden');
        }
    });

    // Initialize sort button active state
    updateSortButtonStates();

    // Load player names for autocomplete (settings modal is visible by default on page load)
    loadPlayerNamesForSettings();

    // Try to restore existing game, or start new one
    restoreOrStartGame();
}

// Start the game when page loads
document.addEventListener('DOMContentLoaded', init);
