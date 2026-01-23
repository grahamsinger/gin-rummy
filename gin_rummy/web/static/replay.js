/**
 * Hand Replay Component
 * Shared component for viewing turn-by-turn hand replays.
 * Used by both Score History modal and History Explorer page.
 */

// Wrap in IIFE to avoid polluting global namespace (game.js also defines SUIT_SYMBOLS)
(function() {
    // Card rendering utilities (scoped to this IIFE)
    const REPLAY_SUIT_SYMBOLS = {
        'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'
    };

    const REPLAY_SUIT_COLORS = {
        'S': 'black', 'H': 'red', 'D': 'red', 'C': 'black'
    };

    /**
     * Format a card ID (e.g., "7H") into display format with suit symbol
     */
    function formatCard(cardId) {
        if (!cardId) return '';
        const suit = cardId.slice(-1);
        const rank = cardId.slice(0, -1);
        return `${rank}${REPLAY_SUIT_SYMBOLS[suit] || suit}`;
    }

    /**
     * Get the color class for a card based on its suit
     */
    function getCardColorClass(cardId) {
        if (!cardId) return '';
        const suit = cardId.slice(-1);
        return REPLAY_SUIT_COLORS[suit] === 'red' ? 'red-card' : 'black-card';
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
     * HandReplay class - manages replay state and rendering
     */
    class HandReplay {
        constructor(containerId, options = {}) {
            this.container = document.getElementById(containerId);
            this.options = {
                showControls: true,
                showTurnList: true,
                onClose: null,
                ...options
            };

            this.handId = null;
            this.turns = [];
            this.currentTurnIndex = 0;
            this.player1Name = '';
            this.player2Name = '';
            this.playerFilter = 'all';  // 'all', 'player1', 'player2'
        }

        /**
         * Load and display a hand replay
         */
        async loadHand(handId, player1Name = 'Player 1', player2Name = 'Player 2') {
            this.handId = handId;
            this.player1Name = player1Name;
            this.player2Name = player2Name;
            this.currentTurnIndex = 0;
            this.playerFilter = 'all';  // Reset filter on new hand

            try {
                const response = await fetch(`/api/hands/${handId}/turns`);
                if (!response.ok) {
                    throw new Error(`Failed to load turns: ${response.statusText}`);
                }

                const data = await response.json();
                this.turns = data.turns || [];

                if (this.turns.length === 0) {
                    this.renderNoTurns();
                    return;
                }

                this.render();
            } catch (error) {
                console.error('Error loading hand replay:', error);
                this.renderError(error.message);
            }
        }

        /**
         * Check if a turn passes the current filter
         */
        turnPassesFilter(turn) {
            if (this.playerFilter === 'all') return true;
            if (this.playerFilter === 'player1') return turn.player_name === this.player1Name;
            if (this.playerFilter === 'player2') return turn.player_name === this.player2Name;
            return true;
        }

        /**
         * Get indices of turns that pass the current filter
         */
        getFilteredIndices() {
            return this.turns
                .map((turn, index) => ({ turn, index }))
                .filter(({ turn }) => this.turnPassesFilter(turn))
                .map(({ index }) => index);
        }

        /**
         * Set the player filter and navigate to nearest visible turn
         */
        setPlayerFilter(filter) {
            this.playerFilter = filter;

            // If current turn doesn't pass filter, find nearest one that does
            if (!this.turnPassesFilter(this.turns[this.currentTurnIndex])) {
                const filteredIndices = this.getFilteredIndices();
                if (filteredIndices.length > 0) {
                    // Find nearest filtered index
                    let nearest = filteredIndices[0];
                    let minDist = Math.abs(this.currentTurnIndex - nearest);
                    for (const idx of filteredIndices) {
                        const dist = Math.abs(this.currentTurnIndex - idx);
                        if (dist < minDist) {
                            minDist = dist;
                            nearest = idx;
                        }
                    }
                    this.currentTurnIndex = nearest;
                }
            }

            this.render();
        }

        /**
         * Navigate to a specific turn
         */
        goToTurn(index) {
            if (index >= 0 && index < this.turns.length) {
                this.currentTurnIndex = index;
                this.render();
            }
        }

        /**
         * Go to the next turn (respects filter)
         */
        nextTurn() {
            const filteredIndices = this.getFilteredIndices();
            const currentFilteredPos = filteredIndices.indexOf(this.currentTurnIndex);
            if (currentFilteredPos >= 0 && currentFilteredPos < filteredIndices.length - 1) {
                this.goToTurn(filteredIndices[currentFilteredPos + 1]);
            } else if (currentFilteredPos === -1) {
                // Current turn not in filter, find next one after current
                const nextIdx = filteredIndices.find(i => i > this.currentTurnIndex);
                if (nextIdx !== undefined) this.goToTurn(nextIdx);
            }
        }

        /**
         * Go to the previous turn (respects filter)
         */
        prevTurn() {
            const filteredIndices = this.getFilteredIndices();
            const currentFilteredPos = filteredIndices.indexOf(this.currentTurnIndex);
            if (currentFilteredPos > 0) {
                this.goToTurn(filteredIndices[currentFilteredPos - 1]);
            } else if (currentFilteredPos === -1) {
                // Current turn not in filter, find prev one before current
                const prevIdx = [...filteredIndices].reverse().find(i => i < this.currentTurnIndex);
                if (prevIdx !== undefined) this.goToTurn(prevIdx);
            }
        }

        /**
         * Go to the first turn (respects filter)
         */
        firstTurn() {
            const filteredIndices = this.getFilteredIndices();
            if (filteredIndices.length > 0) {
                this.goToTurn(filteredIndices[0]);
            }
        }

        /**
         * Go to the last turn (respects filter)
         */
        lastTurn() {
            const filteredIndices = this.getFilteredIndices();
            if (filteredIndices.length > 0) {
                this.goToTurn(filteredIndices[filteredIndices.length - 1]);
            }
        }

        /**
         * Main render function
         */
        render() {
            const turn = this.turns[this.currentTurnIndex];

            this.container.innerHTML = `
                <div class="replay-container">
                    ${this.options.onClose ? `<button class="replay-close-btn" onclick="handReplay.close()">&times;</button>` : ''}

                    <div class="replay-header">
                        <h3>Hand #${this.handId} - Turn ${this.currentTurnIndex + 1} of ${this.turns.length}</h3>
                        <div class="replay-player-name">${turn.player_name}'s turn</div>
                    </div>

                    ${this.options.showControls ? this.renderControls() : ''}

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

                    ${this.renderDeadwoodGraph()}

                    ${this.renderAIReasoning(turn)}

                    ${this.options.showTurnList ? this.renderTurnList() : ''}
                </div>
            `;

            this.attachEventListeners();
        }

        /**
         * Render navigation controls
         */
        renderControls() {
            const filteredIndices = this.getFilteredIndices();
            const currentFilteredPos = filteredIndices.indexOf(this.currentTurnIndex);
            const isFirst = currentFilteredPos <= 0;
            const isLast = currentFilteredPos >= filteredIndices.length - 1;

            // Position display shows filtered position if filter is active
            const positionDisplay = this.playerFilter === 'all'
                ? `${this.currentTurnIndex + 1} / ${this.turns.length}`
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
                    <button class="filter-btn ${this.playerFilter === 'all' ? 'active' : ''}" data-filter="all">All</button>
                    <button class="filter-btn ${this.playerFilter === 'player1' ? 'active' : ''}" data-filter="player1">${this.player1Name}</button>
                    <button class="filter-btn ${this.playerFilter === 'player2' ? 'active' : ''}" data-filter="player2">${this.player2Name}</button>
                </div>
            `;
        }

        /**
         * Render the turn list for quick navigation
         */
        renderTurnList() {
            const turnItems = this.turns.map((turn, index) => {
                const isActive = index === this.currentTurnIndex;
                const colorClass = turn.player_name === this.player1Name ? 'player1' : 'player2';
                const isFiltered = !this.turnPassesFilter(turn);
                return `
                    <div class="turn-list-item ${isActive ? 'active' : ''} ${colorClass} ${isFiltered ? 'filtered-out' : ''}" data-turn-index="${index}">
                        <span class="turn-number">${index + 1}</span>
                        <span class="turn-player">${turn.player_name} <span class="turn-deadwood">(${turn.deadwood_after})</span></span>
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
        renderDeadwoodGraph() {
            if (this.turns.length < 2) return '';

            // Graph dimensions
            const width = 400;
            const height = 120;
            const padding = { top: 15, right: 15, bottom: 25, left: 35 };
            const graphWidth = width - padding.left - padding.right;
            const graphHeight = height - padding.top - padding.bottom;

            // Separate turns by player and build data points
            const player1Data = [];  // Human player
            const player2Data = [];  // Computer

            this.turns.forEach((turn, index) => {
                const point = { turn: index + 1, deadwood: turn.deadwood_after };
                if (turn.player_name === this.player1Name) {
                    player1Data.push(point);
                } else {
                    player2Data.push(point);
                }
            });

            // Find max deadwood for y-axis scale
            const allDeadwood = this.turns.map(t => Math.max(t.deadwood_before, t.deadwood_after));
            const maxDeadwood = Math.max(50, ...allDeadwood);  // At least 50 for scale
            const numTurns = this.turns.length;

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
            const currentTurn = this.turns[this.currentTurnIndex];
            const currentX = xScale(this.currentTurnIndex + 1);
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
                            <span class="legend-item player1-legend"><span class="legend-dot"></span>${this.player1Name}</span>
                            <span class="legend-item player2-legend"><span class="legend-dot"></span>${this.player2Name}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        /**
         * Render AI reasoning section for a turn
         */
        renderAIReasoning(turn) {
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
                            ${d.factors.map(f => `<li>${this.escapeHtml(f)}</li>`).join('')}
                        </ul>
                    </details>
                ` : '';

                return `
                    <div class="ai-decision ai-decision-${d.decision_type}">
                        <div class="ai-decision-header">
                            <span class="ai-decision-icon">${typeIcon}</span>
                            <span class="ai-decision-type">${typeLabel}:</span>
                            <span class="ai-decision-choice">${this.escapeHtml(d.choice)}</span>
                        </div>
                        <div class="ai-decision-reasoning">${this.escapeHtml(d.reasoning)}</div>
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
         * Escape HTML to prevent XSS
         */
        escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        /**
         * Render error state
         */
        renderError(message) {
            this.container.innerHTML = `
                <div class="replay-container replay-error">
                    <h3>Error Loading Replay</h3>
                    <p>${message}</p>
                    ${this.options.onClose ? `<button class="replay-btn" onclick="handReplay.close()">Close</button>` : ''}
                </div>
            `;
        }

        /**
         * Render no turns state
         */
        renderNoTurns() {
            this.container.innerHTML = `
                <div class="replay-container replay-empty">
                    <h3>No Turns Recorded</h3>
                    <p>This hand has no turn data available.</p>
                    ${this.options.onClose ? `<button class="replay-btn" onclick="handReplay.close()">Close</button>` : ''}
                </div>
            `;
        }

        /**
         * Attach event listeners for controls and turn list
         */
        attachEventListeners() {
            // Navigation buttons
            this.container.querySelectorAll('.replay-btn[data-action]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const action = btn.dataset.action;
                    switch (action) {
                        case 'first': this.firstTurn(); break;
                        case 'prev': this.prevTurn(); break;
                        case 'next': this.nextTurn(); break;
                        case 'last': this.lastTurn(); break;
                    }
                });
            });

            // Filter buttons
            this.container.querySelectorAll('.filter-btn[data-filter]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const filter = btn.dataset.filter;
                    this.setPlayerFilter(filter);
                });
            });

            // Turn list items
            this.container.querySelectorAll('.turn-list-item').forEach(item => {
                item.addEventListener('click', () => {
                    const index = parseInt(item.dataset.turnIndex, 10);
                    this.goToTurn(index);
                });
            });

            // Keyboard navigation
            document.addEventListener('keydown', this.handleKeydown.bind(this));
        }

        /**
         * Handle keyboard navigation
         */
        handleKeydown(e) {
            if (!this.container.querySelector('.replay-container')) return;

            switch (e.key) {
                case 'ArrowLeft':
                    this.prevTurn();
                    e.preventDefault();
                    break;
                case 'ArrowRight':
                    this.nextTurn();
                    e.preventDefault();
                    break;
                case 'Home':
                    this.firstTurn();
                    e.preventDefault();
                    break;
                case 'End':
                    this.lastTurn();
                    e.preventDefault();
                    break;
                case 'Escape':
                    if (this.options.onClose) {
                        this.close();
                        e.preventDefault();
                    }
                    break;
            }
        }

        /**
         * Close the replay (if onClose callback provided)
         */
        close() {
            if (this.options.onClose) {
                document.removeEventListener('keydown', this.handleKeydown.bind(this));
                this.options.onClose();
            }
        }

        /**
         * Clear the replay container
         */
        clear() {
            this.container.innerHTML = '';
            this.turns = [];
            this.handId = null;
        }
    }

    // Export for use in other scripts
    window.HandReplay = HandReplay;
})();
