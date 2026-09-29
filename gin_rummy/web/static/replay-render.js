/**
 * Hand replay rendering.
 * Pure functions that turn a HandReplay's state (turns, current index, filter,
 * player names) into HTML strings. No DOM access and no event handling: that
 * stays in replay.js, which owns the state these functions read.
 */

import { escapeHtml, formatCardId, isRedId } from './card-utils.js';

// Card rendering utilities - shared definitions from card-utils.js
const formatCard = formatCardId;

/**
 * Get the color class for a card based on its suit
 */
function getCardColorClass(cardId) {
    if (!cardId) return '';
    return isRedId(cardId) ? 'red-card' : 'black-card';
}

/**
 * Render a list of cards as HTML (simple, no meld grouping)
 */
function renderCards(cards, highlightCard = null) {
    if (!cards || cards.length === 0) return '<span class="no-cards">No cards</span>';

    return cards.map(card => {
        const formatted = formatCard(card);
        const colorClass = getCardColorClass(card);
        const highlightClass = card === highlightCard ? 'highlight-card' : '';
        return `<span class="replay-card ${colorClass} ${highlightClass}">${formatted}</span>`;
    }).join(' ');
}

/**
 * Render a list of cards with melds grouped visually
 */
function renderCardsWithMelds(cards, melds, highlightCard = null) {
    if (!cards || cards.length === 0) return '<span class="no-cards">No cards</span>';

    // If no melds, fall back to simple rendering
    if (!melds || melds.length === 0) {
        return renderCards(cards, highlightCard);
    }

    // Build set of cards in each meld
    const cardToMeldIdx = new Map();
    melds.forEach((meld, idx) => {
        meld.cards.forEach(card => cardToMeldIdx.set(card, idx));
    });

    // Group cards by meld
    const meldGroups = new Map();
    const deadwoodCards = [];

    cards.forEach(card => {
        if (cardToMeldIdx.has(card)) {
            const meldIdx = cardToMeldIdx.get(card);
            if (!meldGroups.has(meldIdx)) {
                meldGroups.set(meldIdx, { cards: [], type: melds[meldIdx].type });
            }
            meldGroups.get(meldIdx).cards.push(card);
        } else {
            deadwoodCards.push(card);
        }
    });

    let html = '';

    // Render meld groups
    meldGroups.forEach((group, idx) => {
        const meldTypeClass = group.type === 'run' ? 'meld-run' : 'meld-set';
        html += `<span class="replay-meld-group ${meldTypeClass}">`;
        html += group.cards.map(card => {
            const formatted = formatCard(card);
            const colorClass = getCardColorClass(card);
            const highlightClass = card === highlightCard ? 'highlight-card' : '';
            return `<span class="replay-card melded ${colorClass} ${highlightClass}">${formatted}</span>`;
        }).join(' ');
        html += '</span> ';
    });

    // Render deadwood cards
    if (deadwoodCards.length > 0) {
        html += deadwoodCards.map(card => {
            const formatted = formatCard(card);
            const colorClass = getCardColorClass(card);
            const highlightClass = card === highlightCard ? 'highlight-card' : '';
            return `<span class="replay-card deadwood ${colorClass} ${highlightClass}">${formatted}</span>`;
        }).join(' ');
    }

    return html;
}

/**
 * The whole replay view for the current turn
 */
export function renderReplay(replay) {
    const turn = replay.turns[replay.currentTurnIndex];

    return `
        <div class="replay-container">
            ${replay.options.onClose ? `<button class="replay-close-btn" data-action="close">&times;</button>` : ''}

            <div class="replay-header">
                <h3>Hand #${replay.handId} - Turn ${replay.currentTurnIndex + 1} of ${replay.turns.length}</h3>
                <div class="replay-player-name">${escapeHtml(turn.player_name)}'s turn</div>
            </div>

            ${replay.options.showControls ? renderControls(replay) : ''}

            <div class="replay-turn-details">
                <div class="replay-action">
                    <strong>Action:</strong>
                    Drew <span class="replay-card ${getCardColorClass(turn.card_drawn)}">${formatCard(turn.card_drawn)}</span>
                    from <span class="draw-source">${turn.drew_from}</span>,
                    discarded <span class="replay-card ${getCardColorClass(turn.card_discarded)}">${formatCard(turn.card_discarded)}</span>
                    ${turn.did_knock ? '<span class="knock-badge">KNOCKED!</span>' : ''}
                </div>

                <div class="replay-deadwood">
                    <strong>Deadwood:</strong>
                    ${turn.deadwood_before} → ${turn.deadwood_after}
                    <span class="deadwood-change ${turn.deadwood_after < turn.deadwood_before ? 'improved' : turn.deadwood_after > turn.deadwood_before ? 'worsened' : ''}">
                        (${turn.deadwood_after < turn.deadwood_before ? '-' : '+'}${Math.abs(turn.deadwood_after - turn.deadwood_before)})
                    </span>
                </div>
            </div>

            <div class="replay-hands">
                <div class="replay-hand-section">
                    <h4>Hand Before</h4>
                    <div class="replay-cards">${renderCardsWithMelds(turn.cards_before, turn.melds_before, turn.card_drawn)}</div>
                </div>
                <div class="replay-hand-section">
                    <h4>Hand After</h4>
                    <div class="replay-cards">${renderCardsWithMelds(turn.cards_after, turn.melds_after)}</div>
                </div>
            </div>

            ${renderDeadwoodGraph(replay)}

            ${renderAIReasoning(turn)}

            ${replay.options.showTurnList ? renderTurnList(replay) : ''}
        </div>
    `;
}

/**
 * Render navigation controls
 */
export function renderControls(replay) {
    const filteredIndices = replay.getFilteredIndices();
    const currentFilteredPos = filteredIndices.indexOf(replay.currentTurnIndex);
    const isFirst = currentFilteredPos <= 0;
    const isLast = currentFilteredPos >= filteredIndices.length - 1;

    // Position display shows filtered position if filter is active
    const positionDisplay = replay.playerFilter === 'all'
        ? `${replay.currentTurnIndex + 1} / ${replay.turns.length}`
        : `${currentFilteredPos + 1} / ${filteredIndices.length} (filtered)`;

    return `
        <div class="replay-controls">
            <button class="replay-btn" ${isFirst ? 'disabled' : ''} data-action="first">|◀</button>
            <button class="replay-btn" ${isFirst ? 'disabled' : ''} data-action="prev">◀</button>
            <span class="replay-position">${positionDisplay}</span>
            <button class="replay-btn" ${isLast ? 'disabled' : ''} data-action="next">▶</button>
            <button class="replay-btn" ${isLast ? 'disabled' : ''} data-action="last">▶|</button>
        </div>
        <div class="replay-filter">
            <span class="filter-label">Show:</span>
            <button class="filter-btn ${replay.playerFilter === 'all' ? 'active' : ''}" data-filter="all">All</button>
            <button class="filter-btn ${replay.playerFilter === 'player1' ? 'active' : ''}" data-filter="player1">${escapeHtml(replay.player1Name)}</button>
            <button class="filter-btn ${replay.playerFilter === 'player2' ? 'active' : ''}" data-filter="player2">${escapeHtml(replay.player2Name)}</button>
        </div>
    `;
}

/**
 * Render the turn list for quick navigation
 */
export function renderTurnList(replay) {
    const turnItems = replay.turns.map((turn, index) => {
        const isActive = index === replay.currentTurnIndex;
        const colorClass = turn.player_name === replay.player1Name ? 'player1' : 'player2';
        const isFiltered = !replay.turnPassesFilter(turn);
        return `
            <div class="turn-list-item ${isActive ? 'active' : ''} ${colorClass} ${isFiltered ? 'filtered-out' : ''}" data-turn-index="${index}">
                <span class="turn-number">${index + 1}</span>
                <span class="turn-deadwood">${turn.deadwood_after}</span>
                <span class="turn-player">${escapeHtml(turn.player_name)}</span>
                <span class="turn-action">${formatCard(turn.card_drawn)} → ${formatCard(turn.card_discarded)}</span>
                ${turn.did_knock ? '<span class="knock-indicator">K</span>' : ''}
            </div>
        `;
    }).join('');

    return `
        <div class="replay-turn-list">
            <h4>All Turns</h4>
            <div class="turn-list-scroll">
                ${turnItems}
            </div>
        </div>
    `;
}

/**
 * Render deadwood progression graph
 */
export function renderDeadwoodGraph(replay) {
    if (replay.turns.length < 2) return '';

    // Graph dimensions
    const width = 400;
    const height = 120;
    const padding = { top: 15, right: 15, bottom: 25, left: 35 };
    const graphWidth = width - padding.left - padding.right;
    const graphHeight = height - padding.top - padding.bottom;

    // Separate turns by player and build data points
    const player1Data = [];  // Human player
    const player2Data = [];  // Computer

    replay.turns.forEach((turn, index) => {
        const point = { turn: index + 1, deadwood: turn.deadwood_after };
        if (turn.player_name === replay.player1Name) {
            player1Data.push(point);
        } else {
            player2Data.push(point);
        }
    });

    // Find max deadwood for y-axis scale
    const allDeadwood = replay.turns.map(t => Math.max(t.deadwood_before, t.deadwood_after));
    const maxDeadwood = Math.max(50, ...allDeadwood);  // At least 50 for scale
    const numTurns = replay.turns.length;

    // Scale functions
    const xScale = (turnNum) => padding.left + ((turnNum - 1) / Math.max(1, numTurns - 1)) * graphWidth;
    const yScale = (dw) => padding.top + (1 - dw / maxDeadwood) * graphHeight;

    // Generate path for a dataset
    const generatePath = (data) => {
        if (data.length === 0) return '';
        return data.map((p, i) =>
            `${i === 0 ? 'M' : 'L'} ${xScale(p.turn).toFixed(1)} ${yScale(p.deadwood).toFixed(1)}`
        ).join(' ');
    };

    // Generate Y-axis labels (0, 25, 50, etc.)
    const yLabels = [];
    const yStep = maxDeadwood <= 30 ? 10 : 25;
    for (let y = 0; y <= maxDeadwood; y += yStep) {
        yLabels.push(`
            <text x="${padding.left - 5}" y="${yScale(y)}" class="graph-label" text-anchor="end" dominant-baseline="middle">${y}</text>
            <line x1="${padding.left}" y1="${yScale(y)}" x2="${width - padding.right}" y2="${yScale(y)}" class="graph-grid" />
        `);
    }

    // Current turn indicator
    const currentTurn = replay.turns[replay.currentTurnIndex];
    const currentX = xScale(replay.currentTurnIndex + 1);
    const currentY = yScale(currentTurn.deadwood_after);

    return `
        <div class="deadwood-graph-section">
            <h4>Deadwood Progression</h4>
            <div class="deadwood-graph-container">
                <svg class="deadwood-graph" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
                    <!-- Grid lines -->
                    ${yLabels.join('')}

                    <!-- X-axis -->
                    <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" class="graph-axis" />

                    <!-- Y-axis -->
                    <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" class="graph-axis" />

                    <!-- Player 1 line (human) -->
                    <path d="${generatePath(player1Data)}" class="graph-line player1-line" fill="none" />

                    <!-- Player 2 line (computer) -->
                    <path d="${generatePath(player2Data)}" class="graph-line player2-line" fill="none" />

                    <!-- Data points for player 1 -->
                    ${player1Data.map(p => `
                        <circle cx="${xScale(p.turn)}" cy="${yScale(p.deadwood)}" r="3" class="graph-point player1-point" />
                    `).join('')}

                    <!-- Data points for player 2 -->
                    ${player2Data.map(p => `
                        <circle cx="${xScale(p.turn)}" cy="${yScale(p.deadwood)}" r="3" class="graph-point player2-point" />
                    `).join('')}

                    <!-- Current turn indicator -->
                    <circle cx="${currentX}" cy="${currentY}" r="6" class="graph-current-point" />

                    <!-- X-axis label -->
                    <text x="${width / 2}" y="${height - 3}" class="graph-label" text-anchor="middle">Turn</text>
                </svg>
                <div class="graph-legend">
                    <span class="legend-item player1-legend"><span class="legend-dot"></span>${escapeHtml(replay.player1Name)}</span>
                    <span class="legend-item player2-legend"><span class="legend-dot"></span>${escapeHtml(replay.player2Name)}</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * Render AI reasoning section for a turn
 */
export function renderAIReasoning(turn) {
    // Only show AI reasoning for Computer turns
    if (turn.player_name !== 'Computer' || !turn.ai_decisions?.length) {
        return '';
    }

    const decisions = turn.ai_decisions.map(d => {
        const typeIcon = {
            'draw': '🎴',
            'discard': '🗑️',
            'knock': '🚪'
        }[d.decision_type] || '📋';

        const typeLabel = d.decision_type.charAt(0).toUpperCase() + d.decision_type.slice(1);

        const factorsHtml = d.factors?.length ? `
            <details class="ai-factors">
                <summary>Factors (${d.factors.length})</summary>
                <ul>
                    ${d.factors.map(f => `<li>${escapeHtml(f)}</li>`).join('')}
                </ul>
            </details>
        ` : '';

        // Discard choices are stored as card codes ("KD"); older rows hold the
        // display string ("K♦"). Format codes, pass anything else through.
        const choiceText = /^(10|[2-9AJQK])[SHDC]$/.test(d.choice) ? formatCard(d.choice) : d.choice;
        return `
            <div class="ai-decision ai-decision-${d.decision_type}">
                <div class="ai-decision-header">
                    <span class="ai-decision-icon">${typeIcon}</span>
                    <span class="ai-decision-type">${typeLabel}:</span>
                    <span class="ai-decision-choice">${escapeHtml(choiceText)}</span>
                </div>
                <div class="ai-decision-reasoning">${escapeHtml(d.reasoning)}</div>
                ${factorsHtml}
            </div>
        `;
    }).join('');

    return `
        <div class="ai-reasoning-section">
            <h4>🤖 AI Reasoning</h4>
            <div class="ai-decisions">
                ${decisions}
            </div>
        </div>
    `;
}

/**
 * Render error state
 */
export function renderError(message, showClose) {
    return `
        <div class="replay-container replay-error">
            <h3>Error Loading Replay</h3>
            <p>${message}</p>
            ${showClose ? `<button class="replay-btn" data-action="close">Close</button>` : ''}
        </div>
    `;
}

/**
 * Render no turns state
 */
export function renderNoTurns(showClose) {
    return `
        <div class="replay-container replay-empty">
            <h3>No Turns Recorded</h3>
            <p>This hand has no turn data available.</p>
            ${showClose ? `<button class="replay-btn" data-action="close">Close</button>` : ''}
        </div>
    `;
}
