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
    replayContainer: document.getElementById('history-replay-container')
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
 * Render a single game card
 */
function renderGameCard(game) {
    const startDate = game.started_at ? formatDate(game.started_at) : 'Unknown date';
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

    return `
        <div class="game-card" data-game-id="${game.game_id}">
            <div class="game-header">
                <div class="game-info">
                    <div class="game-players">${game.player1_name} vs ${game.player2_name}</div>
                    <div class="game-date">${startDate} - ${game.hand_count} hand(s)</div>
                </div>
                <div class="game-result">
                    <div class="game-winner">${winner}</div>
                    <div class="game-score">${score}</div>
                </div>
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

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
