// The settings modal.
import { escapeHtml as esc } from '../card-utils.js';
import { elements } from './dom.js';
import { savedSettings } from './state.js';

export async function showSettingsModal() {
    // Load existing players for autocomplete
    await loadPlayerNamesForSettings();

    // Clear player name initially to show all options in datalist
    // User can then select from list or type a new name
    elements.playerNameInput.value = '';
    elements.playerNameInput.placeholder = savedSettings.playerName || 'Enter name...';
    elements.aiDifficultySelect.value = savedSettings.aiDifficulty;

    // Load saved game mode settings
    const savedGameMode = localStorage.getItem('gameMode') || 'target';
    const savedTargetScore = localStorage.getItem('targetScore') || '100';
    elements.gameModeSelect.value = savedGameMode;
    elements.targetScoreSelect.value = savedTargetScore;

    // Show/hide target score field based on mode
    if (savedGameMode === 'target') {
        elements.targetScoreField.style.display = 'flex';
    } else {
        elements.targetScoreField.style.display = 'none';
    }

    // Load Oklahoma Gin settings
    const oklahomaGin = localStorage.getItem('oklahomaGin') === 'true';
    const spadeDoubling = localStorage.getItem('spadeDoubling') !== 'false'; // default true
    const matchMode = localStorage.getItem('matchMode') === 'true';
    elements.oklahomaGinCheckbox.checked = oklahomaGin;
    elements.spadeDoublingCheckbox.checked = spadeDoubling;
    elements.matchModeCheckbox.checked = matchMode;

    // Show spade doubling field if Oklahoma is checked
    elements.spadeDoublingField.style.display = oklahomaGin ? 'flex' : 'none';

    elements.settingsModal.classList.remove('hidden');

    // Focus on player name input
    setTimeout(() => elements.playerNameInput.focus(), 100);
}

export async function loadPlayerNamesForSettings() {
    try {
        const response = await fetch('/api/players');
        const players = await response.json();

        // Populate datalist with all players EXCEPT "Computer"
        elements.playerNamesList.innerHTML = players
            .filter(p => p.name !== 'Computer')
            .map(p =>
                `<option value="${esc(p.name)}">${esc(p.name)} (${p.total_hands} hands, ${(p.win_rate * 100).toFixed(0)}% wins)</option>`
            ).join('');
    } catch (error) {
        console.error('Failed to load player names:', error);
        // Silently fail - user can still type a name
    }
}
