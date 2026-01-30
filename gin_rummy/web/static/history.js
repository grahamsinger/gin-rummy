/**
 * History Explorer Page
 * Browse and replay past games and hands.
 */

// State
let currentPage = 0;
const pageSize = 20;
let totalGames = 0;
let currentFilter = '';
let handReplay = null;

let pendingDeleteGameId = null;

// DOM Elements
const elements = {
    playerFilter: document.getElementById('player-filter'),
    applyFilters: document.getElementById('apply-filters'),
    gamesContainer: document.getElementById('games-container'),
    pagination: document.getElementById('pagination'),
    prevPage: document.getElementById('prev-page'),
    nextPage: document.getElementById('next-page'),
    pageInfo: document.getElementById('page-info'),
    replayPanel: document.getElementById('replay-panel'),
    replayContainer: document.getElementById('history-replay-container'),
    deleteModal: document.getElementById('delete-modal'),
    deleteModalText: document.getElementById('delete-modal-text'),
    deleteCancel: document.getElementById('delete-cancel'),
    deleteConfirm: document.getElementById('delete-confirm'),
};

/**
 * Initialize the page
 */
async function init() {
    // Load player list for filter
    await loadPlayers();

    // Load initial games
    await loadGames();

    // Set up event listeners
    elements.applyFilters.addEventListener('click', () => {
        currentPage = 0;
        currentFilter = elements.playerFilter.value;
        loadGames();
    });

    elements.prevPage.addEventListener('click', () => {
        if (currentPage > 0) {
            currentPage--;
            loadGames();
        }
    });

    elements.nextPage.addEventListener('click', () => {
        currentPage++;
        loadGames();
    });

    elements.deleteCancel.addEventListener('click', hideDeleteModal);
    elements.deleteConfirm.addEventListener('click', confirmDelete);
    elements.deleteModal.addEventListener('click', (e) => {
        if (e.target === elements.deleteModal) hideDeleteModal();
    });
}

/**
 * Load player list for filter dropdown
 */
async function loadPlayers() {
    try {
        const response = await fetch('/api/players');
        const players = await response.json();

        // Add players to dropdown
        players.forEach(player => {
            const option = document.createElement('option');
            option.value = player.name;
            option.textContent = player.name;
            elements.playerFilter.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load players:', error);
    }
}

/**
 * Load games from API
 */
async function loadGames() {
    elements.gamesContainer.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading game history...</p>
        </div>
    `;

    try {
        let url = `/api/history?limit=${pageSize}&offset=${currentPage * pageSize}`;
        if (currentFilter) {
            url += `&player_name=${encodeURIComponent(currentFilter)}`;
        }

        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load history');

        const data = await response.json();
        renderGames(data.games);
        updatePagination(data.games.length);

    } catch (error) {
        console.error('Failed to load games:', error);
        elements.gamesContainer.innerHTML = `
            <div class="empty-state">
                <p>Failed to load game history. Please try again.</p>
            </div>
        `;
    }
}

/**
 * Render games list
 */
function renderGames(games) {
    if (!games || games.length === 0) {
        elements.gamesContainer.innerHTML = `
            <div class="empty-state">
                <p>No games found.</p>
            </div>
        `;
        return;
    }

    const html = games.map(game => renderGameCard(game)).join('');
    elements.gamesContainer.innerHTML = html;

    // Add event listeners for expanding games
    elements.gamesContainer.querySelectorAll('.game-header').forEach(header => {
        header.addEventListener('click', (e) => {
            const card = header.closest('.game-card');
            card.classList.toggle('expanded');
        });
    });

    // Add event listeners for delete buttons
    elements.gamesContainer.querySelectorAll('.delete-game-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const gameId = parseInt(btn.dataset.gameId, 10);
            const players = btn.dataset.players;
            showDeleteModal(gameId, players);
        });
    });

    // Add event listeners for hand rows
    elements.gamesContainer.querySelectorAll('.hand-row').forEach(row => {
        row.addEventListener('click', (e) => {
            e.stopPropagation();
            const handId = parseInt(row.dataset.handId, 10);
            const p1 = row.dataset.player1;
            const p2 = row.dataset.player2;
            openReplay(handId, p1, p2);
        });
    });
}

/**
 * Format game settings into a compact summary string.
 * Returns empty string if no settings are stored (old games).
 */
function formatGameSettings(game) {
    const parts = [];

    if (game.ai_difficulty) {
        const label = game.ai_difficulty.charAt(0).toUpperCase() + game.ai_difficulty.slice(1);
        parts.push(`${label} AI`);
    }

    if (game.oklahoma_gin) {
        parts.push('Oklahoma Gin');
    }

    if (game.spade_doubling) {
        parts.push('Spade Doubling');
    }

    if (game.match_mode) {
        parts.push('Match');
    }

    if (game.game_mode === 'target' && game.target_score) {
        parts.push(`Target: ${game.target_score}`);
    }

    return parts.join(' · ');
}

/**
 * Render a single game card
 */
function renderGameCard(game) {
    const startDate = game.started_at ? formatDate(game.started_at) : 'Unknown date';
    const relTime = game.started_at ? formatRelativeTime(game.started_at) : '';
    const dateDisplay = relTime ? `${startDate} (${relTime})` : startDate;
    const winner = game.winner_name || 'In Progress';
    const score = game.final_score_p1 !== null && game.final_score_p2 !== null
        ? `${game.final_score_p1} - ${game.final_score_p2}`
        : '';

    let handsHtml = '';
    if (game.hands && game.hands.length > 0) {
        handsHtml = `
            <table class="hands-table">
                <thead>
                    <tr>
                        <th>Hand</th>
                        <th>Winner</th>
                        <th>Points</th>
                    </tr>
                </thead>
                <tbody>
                    ${game.hands.map(hand => renderHandRow(hand, game.player1_name, game.player2_name)).join('')}
                </tbody>
            </table>
        `;
    } else {
        handsHtml = '<p style="color: rgba(255,255,255,0.5);">No hands recorded</p>';
    }

    const settingsText = formatGameSettings(game);

    return `
        <div class="game-card" data-game-id="${game.game_id}">
            <div class="game-header">
                <div class="game-info">
                    <div class="game-players">${game.player1_name} vs ${game.player2_name}</div>
                    <div class="game-date">${dateDisplay} - ${game.hand_count} hand(s)</div>
                    ${settingsText ? `<div class="game-settings">${settingsText}</div>` : ''}
                </div>
                <div class="game-result">
                    <div class="game-winner">${winner}</div>
                    <div class="game-score">${score}</div>
                </div>
                <button class="delete-game-btn" data-game-id="${game.game_id}" data-players="${game.player1_name} vs ${game.player2_name}" title="Delete game">&#128465;</button>
                <span class="game-expand-icon">▼</span>
            </div>
            <div class="game-hands">
                ${handsHtml}
            </div>
        </div>
    `;
}

/**
 * Render a single hand row
 */
function renderHandRow(hand, player1Name, player2Name) {
    let badges = '';
    if (hand.is_gin) badges += '<span class="hand-badge gin">GIN</span>';
    if (hand.is_undercut) badges += '<span class="hand-badge undercut">UNDERCUT</span>';
    if (hand.is_draw) badges += '<span class="hand-badge draw">DRAW</span>';

    const winner = hand.winner_name || 'Draw';
    const points = hand.points_awarded !== null ? hand.points_awarded : '-';

    return `
        <tr class="hand-row" data-hand-id="${hand.id}" data-player1="${player1Name}" data-player2="${player2Name}" title="Click to view replay">
            <td>Hand ${hand.hand_number}</td>
            <td>${winner}${badges}</td>
            <td>${points}</td>
        </tr>
    `;
}

/**
 * Format date for display
 */
function formatDate(dateStr) {
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return dateStr;
    }
}

/**
 * Format a date string as relative time (e.g. "2 hours ago", "yesterday")
 */
function formatRelativeTime(dateStr) {
    try {
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHr = Math.floor(diffMin / 60);
        const diffDays = Math.floor(diffHr / 24);
        const diffWeeks = Math.floor(diffDays / 7);
        const diffMonths = Math.floor(diffDays / 30);

        if (diffSec < 60) return 'just now';
        if (diffMin === 1) return '1 minute ago';
        if (diffMin < 60) return `${diffMin} minutes ago`;
        if (diffHr === 1) return '1 hour ago';
        if (diffHr < 24) return `${diffHr} hours ago`;
        if (diffDays === 1) return 'yesterday';
        if (diffDays < 7) return `${diffDays} days ago`;
        if (diffWeeks === 1) return '1 week ago';
        if (diffWeeks < 5) return `${diffWeeks} weeks ago`;
        if (diffMonths === 1) return '1 month ago';
        if (diffMonths < 12) return `${diffMonths} months ago`;
        return formatDate(dateStr);
    } catch (e) {
        return '';
    }
}

/**
 * Update pagination controls
 */
function updatePagination(loadedCount) {
    const hasMore = loadedCount === pageSize;
    const hasPrev = currentPage > 0;

    elements.prevPage.disabled = !hasPrev;
    elements.nextPage.disabled = !hasMore;
    elements.pageInfo.textContent = `Page ${currentPage + 1}`;

    elements.pagination.style.display = (hasPrev || hasMore) ? 'flex' : 'none';
}

/**
 * Open replay panel for a hand
 */
function openReplay(handId, player1Name, player2Name) {
    // Show replay panel
    elements.replayPanel.classList.add('visible');

    // Scroll to replay
    elements.replayPanel.scrollIntoView({ behavior: 'smooth' });

    // Create or reuse replay instance
    if (!handReplay) {
        handReplay = new HandReplay('history-replay-container', {
            showControls: true,
            showTurnList: true,
            onClose: closeReplay
        });
    }

    // Load the hand
    handReplay.loadHand(handId, player1Name, player2Name);
}

/**
 * Close replay panel
 */
function closeReplay() {
    elements.replayPanel.classList.remove('visible');
}

/**
 * Show the delete confirmation modal
 */
function showDeleteModal(gameId, players) {
    pendingDeleteGameId = gameId;
    elements.deleteModalText.textContent = `Delete game "${players}"? This cannot be undone.`;
    elements.deleteModal.classList.remove('hidden');
}

/**
 * Hide the delete confirmation modal
 */
function hideDeleteModal() {
    pendingDeleteGameId = null;
    elements.deleteModal.classList.add('hidden');
}

/**
 * Confirm deletion — call API and reload
 */
async function confirmDelete() {
    if (pendingDeleteGameId === null) return;

    const gameId = pendingDeleteGameId;
    hideDeleteModal();

    try {
        const response = await fetch(`/api/games/${gameId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Delete failed');
        await loadGames();
    } catch (error) {
        console.error('Failed to delete game:', error);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
