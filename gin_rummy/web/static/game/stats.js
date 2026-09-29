// The player statistics modal.
import { escapeHtml as esc } from '../card-utils.js';
import { elements } from './dom.js';
import { ui, savedSettings } from './state.js';

// Fetch and display player stats
export async function showPlayerStats() {
    // Get player name from current game state if available, otherwise use saved settings
    let playerName = savedSettings.playerName || 'Player';
    if (ui.gameState && ui.gameState.scores) {
        const playerNames = Object.keys(ui.gameState.scores);
        if (playerNames.length > 0 && playerNames[0] !== 'Computer') {
            playerName = playerNames[0];
        }
    }

    elements.statsModal.classList.remove('hidden');

    // Load player list
    await loadPlayerList();

    // Set current player in selector
    elements.statsPlayerSelect.value = playerName;
    ui.currentViewedPlayer = playerName;

    // Load stats for current player
    await loadStatsForPlayer(playerName);

    // Enable clear button for current player
    elements.clearStatsBtn.disabled = false;
}

async function loadPlayerList() {
    try {
        const response = await fetch('/api/players');
        const players = await response.json();

        // Populate select dropdown with all players
        elements.statsPlayerSelect.innerHTML = players.map(p =>
            `<option value="${esc(p.name)}">${esc(p.name)} (${p.total_hands} hands, ${(p.win_rate * 100).toFixed(0)}% wins)</option>`
        ).join('');

        // If current player not in list, add them
        let currentPlayerName = savedSettings.playerName || 'Player';
        if (ui.gameState && ui.gameState.scores) {
            const playerNames = Object.keys(ui.gameState.scores);
            if (playerNames.length > 0 && playerNames[0] !== 'Computer') {
                currentPlayerName = playerNames[0];
            }
        }
        const playerExists = players.some(p => p.name === currentPlayerName);
        if (!playerExists) {
            elements.statsPlayerSelect.innerHTML =
                `<option value="${esc(currentPlayerName)}">${esc(currentPlayerName)} (0 hands)</option>` +
                elements.statsPlayerSelect.innerHTML;
        }
    } catch (error) {
        console.error('Failed to load player list:', error);
        elements.statsPlayerSelect.innerHTML = '<option value="">Error loading players</option>';
    }
}

export async function loadSelectedPlayerStats() {
    const playerName = elements.statsPlayerSelect.value.trim();
    if (!playerName) return;

    ui.currentViewedPlayer = playerName;
    await loadStatsForPlayer(playerName);

    // Enable/disable clear button based on whether viewing current player
    // Get current player name from game state if available
    let currentPlayerName = savedSettings.playerName || 'Player';
    if (ui.gameState && ui.gameState.scores) {
        const playerNames = Object.keys(ui.gameState.scores);
        if (playerNames.length > 0 && playerNames[0] !== 'Computer') {
            currentPlayerName = playerNames[0];
        }
    }
    const isCurrentPlayer = playerName === currentPlayerName;
    elements.clearStatsBtn.disabled = !isCurrentPlayer;
}

async function loadStatsForPlayer(playerName) {
    elements.statsContent.innerHTML = '<div class="stats-loading">Loading stats...</div>';

    try {
        const response = await fetch(`/api/stats/${encodeURIComponent(playerName)}`);
        const stats = await response.json();

        if (stats.total_hands === 0) {
            elements.statsContent.innerHTML = `
                <div class="stats-empty">
                    <p>No statistics available yet for <strong>${esc(playerName)}</strong>.</p>
                    <p>Play some hands to start tracking stats!</p>
                </div>
            `;
            return;
        }

        // Render stats
        const html = `
            <div class="stats-list">
                <div class="stat-row">
                    <span class="stat-label">Total Hands</span>
                    <span class="stat-value">${stats.total_hands}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Win Rate</span>
                    <span class="stat-value">${(stats.win_rate * 100).toFixed(1)}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Hands Won</span>
                    <span class="stat-value">${stats.hands_won}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Hands Lost</span>
                    <span class="stat-value">${stats.hands_lost}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Avg Deadwood</span>
                    <span class="stat-value">${stats.avg_deadwood.toFixed(1)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Avg Points/Hand</span>
                    <span class="stat-value">${stats.avg_points_per_hand.toFixed(1)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Gins</span>
                    <span class="stat-value">${stats.gins}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Gin Rate</span>
                    <span class="stat-value">${(stats.gin_rate * 100).toFixed(1)}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Undercuts Made</span>
                    <span class="stat-value">${stats.undercuts_made}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Undercut Rate</span>
                    <span class="stat-value">${(stats.undercut_rate * 100).toFixed(1)}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label" title="Percentage of hands where you knocked (knocks / total hands)">Knock Aggression</span>
                    <span class="stat-value">${(stats.knock_aggression * 100).toFixed(1)}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Avg Knock Deadwood</span>
                    <span class="stat-value">${stats.avg_knock_deadwood.toFixed(1)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Deck Draw Rate</span>
                    <span class="stat-value">${(stats.deck_draw_rate * 100).toFixed(1)}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Discard Draw Rate</span>
                    <span class="stat-value">${(stats.discard_draw_rate * 100).toFixed(1)}%</span>
                </div>
            </div>
        `;
        elements.statsContent.innerHTML = html;
    } catch (error) {
        console.error('Failed to load stats:', error);
        elements.statsContent.innerHTML = `
            <div class="stats-error">
                <p>Failed to load statistics.</p>
                <p>Please try again later.</p>
            </div>
        `;
    }
}

export function showClearStatsConfirmation() {
    const playerName = ui.currentViewedPlayer;
    if (!playerName) return;

    elements.clearStatsPlayerName.textContent = playerName;
    elements.clearStatsModal.classList.remove('hidden');
}

export async function confirmClearStats() {
    const playerName = ui.currentViewedPlayer;
    if (!playerName) return;

    try {
        const response = await fetch(`/api/stats/${encodeURIComponent(playerName)}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Failed to delete stats');

        // Close confirmation modal
        elements.clearStatsModal.classList.add('hidden');

        // Reload stats (will show "no stats" message)
        await loadStatsForPlayer(playerName);

        // Reload player list
        await loadPlayerList();

    } catch (error) {
        console.error('Failed to clear stats:', error);
        alert('Failed to clear statistics. Please try again.');
    }
}
