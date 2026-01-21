/**
 * Hand Replay Component
 * Shared component for viewing turn-by-turn hand replays.
 * Used by both Score History modal and History Explorer page.
 */

// Card rendering utilities
const SUIT_SYMBOLS = {
    'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'
};

const SUIT_COLORS = {
    'S': 'black', 'H': 'red', 'D': 'red', 'C': 'black'
};

/**
 * Format a card ID (e.g., "7H") into display format with suit symbol
 */
function formatCard(cardId) {
    if (!cardId) return '';
    const suit = cardId.slice(-1);
    const rank = cardId.slice(0, -1);
    return `${rank}${SUIT_SYMBOLS[suit] || suit}`;
}

/**
 * Get the color class for a card based on its suit
 */
function getCardColorClass(cardId) {
    if (!cardId) return '';
    const suit = cardId.slice(-1);
    return SUIT_COLORS[suit] === 'red' ? 'red-card' : 'black-card';
}

/**
 * Render a list of cards as HTML
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
    }

    /**
     * Load and display a hand replay
     */
    async loadHand(handId, player1Name = 'Player 1', player2Name = 'Player 2') {
        this.handId = handId;
        this.player1Name = player1Name;
        this.player2Name = player2Name;
        this.currentTurnIndex = 0;

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
     * Navigate to a specific turn
     */
    goToTurn(index) {
        if (index >= 0 && index < this.turns.length) {
            this.currentTurnIndex = index;
            this.render();
        }
    }

    /**
     * Go to the next turn
     */
    nextTurn() {
        this.goToTurn(this.currentTurnIndex + 1);
    }

    /**
     * Go to the previous turn
     */
    prevTurn() {
        this.goToTurn(this.currentTurnIndex - 1);
    }

    /**
     * Go to the first turn
     */
    firstTurn() {
        this.goToTurn(0);
    }

    /**
     * Go to the last turn
     */
    lastTurn() {
        this.goToTurn(this.turns.length - 1);
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
                        <div class="replay-cards">${renderCards(turn.cards_before, turn.card_drawn)}</div>
                    </div>
                    <div class="replay-hand-section">
                        <h4>Hand After</h4>
                        <div class="replay-cards">${renderCards(turn.cards_after)}</div>
                    </div>
                </div>

                ${this.options.showTurnList ? this.renderTurnList() : ''}
            </div>
        `;

        this.attachEventListeners();
    }

    /**
     * Render navigation controls
     */
    renderControls() {
        const isFirst = this.currentTurnIndex === 0;
        const isLast = this.currentTurnIndex === this.turns.length - 1;

        return `
            <div class="replay-controls">
                <button class="replay-btn" ${isFirst ? 'disabled' : ''} data-action="first">|◀</button>
                <button class="replay-btn" ${isFirst ? 'disabled' : ''} data-action="prev">◀</button>
                <span class="replay-position">${this.currentTurnIndex + 1} / ${this.turns.length}</span>
                <button class="replay-btn" ${isLast ? 'disabled' : ''} data-action="next">▶</button>
                <button class="replay-btn" ${isLast ? 'disabled' : ''} data-action="last">▶|</button>
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
            return `
                <div class="turn-list-item ${isActive ? 'active' : ''} ${colorClass}" data-turn-index="${index}">
                    <span class="turn-number">${index + 1}</span>
                    <span class="turn-player">${turn.player_name}</span>
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
