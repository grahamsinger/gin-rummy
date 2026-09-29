/**
 * History Explorer Page
 * Browse and replay past games and hands.
 */

import { escapeHtml } from './card-utils.js';
import { HandReplay } from './replay.js';

// Escape user-controlled strings (player names, etc.) before innerHTML.
const esc = escapeHtml;

// State
let currentPage = 0;
const pageSize = 20;
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
    replayModal: document.getElementById('replay-modal'),
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
    elements.replayModal.addEventListener('click', (e) => {
        // Go through the replay so it drops its keydown listener (it calls closeReplay via onClose)
        if (e.target === elements.replayModal) (handReplay ? handReplay.close() : closeReplay());
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

    // Add event listeners for resume buttons
    elements.gamesContainer.querySelectorAll('.resume-game-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const gameId = parseInt(btn.dataset.gameId, 10);
            resumeGame(gameId);
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

    if (game.oklahoma_gin && game.spade_doubling) {
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
    const hasScores = game.final_score_p1 !== null && game.final_score_p2 !== null;
    const scoreDisplay = hasScores
        ? `${esc(game.player1_name)} ${game.final_score_p1} - ${game.final_score_p2} ${esc(game.player2_name)}`
        : '';

    let handsHtml = '';
    if (game.hands && game.hands.length > 0) {
        // Pre-compute cumulative scores for each hand
        let cumP1 = 0;
        let cumP2 = 0;
        const handsWithScores = game.hands.map(hand => {
            const pts = hand.points_awarded || 0;
            if (hand.winner_name === game.player1_name) cumP1 += pts;
            else if (hand.winner_name === game.player2_name) cumP2 += pts;
            return { ...hand, cumP1, cumP2 };
        });

        handsHtml = `
            ${renderScoreGraph(game)}
            <table class="hands-table">
                <thead>
                    <tr>
                        <th></th>
                        <th style="text-align:right">${esc(game.player1_name)}</th>
                        <th style="text-align:center"></th>
                        <th style="text-align:left">${esc(game.player2_name)}</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${handsWithScores.map(hand => renderHandRow(hand, game.player1_name, game.player2_name)).join('')}
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
                    <div class="game-players">${esc(game.player1_name)} vs ${esc(game.player2_name)}</div>
                    <div class="game-date">${dateDisplay} - ${game.hand_count} hand(s)</div>
                    ${settingsText ? `<div class="game-settings">${settingsText}</div>` : ''}
                </div>
                <div class="game-result">
                    <div class="game-winner">${esc(winner)}</div>
                    <div class="game-score">${scoreDisplay}</div>
                </div>
                ${!game.winner_name ? `<button class="resume-game-btn" data-game-id="${game.game_id}" title="Resume game">Resume</button>` : '<span></span>'}
                <button class="delete-game-btn" data-game-id="${game.game_id}" data-players="${esc(game.player1_name)} vs ${esc(game.player2_name)}" title="Delete game"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></button>
                <span class="game-expand-icon">▼</span>
            </div>
            <div class="game-hands">
                ${handsHtml}
            </div>
        </div>
    `;
}

/**
 * Render a score progression graph for a game
 */
function renderScoreGraph(game) {
    if (!game.hands || game.hands.length < 2) return '';

    // Compute cumulative scores from hand data
    const p1Data = [{ hand: 0, score: 0 }];
    const p2Data = [{ hand: 0, score: 0 }];
    let cumP1 = 0;
    let cumP2 = 0;

    game.hands.forEach((hand, idx) => {
        const pts = hand.points_awarded || 0;
        if (hand.winner_name === game.player1_name) {
            cumP1 += pts;
        } else if (hand.winner_name === game.player2_name) {
            cumP2 += pts;
        }
        const handNum = idx + 1;
        p1Data.push({ hand: handNum, score: cumP1 });
        p2Data.push({ hand: handNum, score: cumP2 });
    });

    const maxScore = Math.max(cumP1, cumP2, 25);
    const numHands = game.hands.length;

    // Graph dimensions
    const width = 400;
    const height = 140;
    const padding = { top: 15, right: 15, bottom: 25, left: 40 };
    const graphWidth = width - padding.left - padding.right;
    const graphHeight = height - padding.top - padding.bottom;

    const xScale = (h) => padding.left + (h / numHands) * graphWidth;
    const yScale = (s) => padding.top + (1 - s / maxScore) * graphHeight;

    const generatePath = (data) => {
        return data.map((p, i) =>
            `${i === 0 ? 'M' : 'L'} ${xScale(p.hand).toFixed(1)} ${yScale(p.score).toFixed(1)}`
        ).join(' ');
    };

    // Y-axis labels
    const yStep = maxScore <= 50 ? 10 : maxScore <= 150 ? 25 : 50;
    const yLabels = [];
    for (let y = 0; y <= maxScore; y += yStep) {
        yLabels.push(`
            <text x="${padding.left - 5}" y="${yScale(y)}" class="graph-label" text-anchor="end" dominant-baseline="middle">${y}</text>
            <line x1="${padding.left}" y1="${yScale(y)}" x2="${width - padding.right}" y2="${yScale(y)}" class="graph-grid" />
        `);
    }

    // Target score line
    let targetLine = '';
    if (game.target_score && game.target_score <= maxScore * 1.1) {
        const ty = yScale(game.target_score);
        targetLine = `<line x1="${padding.left}" y1="${ty}" x2="${width - padding.right}" y2="${ty}" stroke="#ffc107" stroke-width="1" stroke-dasharray="4,3" opacity="0.6" />`;
    }

    return `
        <div class="deadwood-graph-section">
            <h4>Score Progression</h4>
            <div class="deadwood-graph-container">
                <svg class="deadwood-graph" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
                    ${yLabels.join('')}
                    <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" class="graph-axis" />
                    <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" class="graph-axis" />
                    ${targetLine}
                    <path d="${generatePath(p1Data)}" class="graph-line player1-line" fill="none" />
                    <path d="${generatePath(p2Data)}" class="graph-line player2-line" fill="none" />
                    ${p1Data.slice(1).map(p => `<circle cx="${xScale(p.hand)}" cy="${yScale(p.score)}" r="3" class="graph-point player1-point" />`).join('')}
                    ${p2Data.slice(1).map(p => `<circle cx="${xScale(p.hand)}" cy="${yScale(p.score)}" r="3" class="graph-point player2-point" />`).join('')}
                    <text x="${width / 2}" y="${height - 3}" class="graph-label" text-anchor="middle">Hand</text>
                </svg>
                <div class="graph-legend">
                    <span class="legend-item player1-legend"><span class="legend-dot"></span>${esc(game.player1_name)}</span>
                    <span class="legend-item player2-legend"><span class="legend-dot"></span>${esc(game.player2_name)}</span>
                </div>
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

    const p1Won = hand.winner_name === player1Name;
    const p2Won = hand.winner_name === player2Name;
    const pts = hand.points_awarded || 0;
    const p1Score = p1Won ? `(+${pts}) <strong>${hand.cumP1}</strong>` : `${hand.cumP1}`;
    const p2Score = p2Won ? `<strong>${hand.cumP2}</strong> (+${pts})` : `${hand.cumP2}`;
    const leftBadges = p1Won ? badges : '';
    const rightBadges = p2Won ? badges : '';

    return `
        <tr class="hand-row" data-hand-id="${hand.id}" data-player1="${esc(player1Name)}" data-player2="${esc(player2Name)}" title="Click to view replay">
            <td>${hand.hand_number}</td>
            <td style="text-align:right">${leftBadges} ${p1Score}</td>
            <td style="text-align:center">-</td>
            <td style="text-align:left">${p2Score} ${rightBadges}</td>
            <td></td>
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
    } catch {
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
    } catch {
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
 * Open replay modal for a hand
 */
function openReplay(handId, player1Name, player2Name) {
    // Show replay modal
    elements.replayModal.classList.remove('hidden');

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
 * Close replay modal
 */
function closeReplay() {
    elements.replayModal.classList.add('hidden');
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

/**
 * Resume a game — POST to API and navigate to game page
 */
async function resumeGame(gameId) {
    try {
        const response = await fetch('/api/game/resume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId }),
        });
        if (!response.ok) throw new Error('Resume failed');
        window.location.href = '/';
    } catch (error) {
        console.error('Failed to resume game:', error);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
