/**
 * Hand Replay Component
 * Shared component for viewing turn-by-turn hand replays: loads the turns,
 * owns the current position and player filter, and handles the controls
 * and keyboard. The HTML itself comes from replay-render.js.
 * Used by both Score History modal and History Explorer page.
 */

import { renderError, renderNoTurns, renderReplay } from './replay-render.js';

/**
 * HandReplay class - loads a hand and drives playback (position, filter, controls, keyboard)
 */
export class HandReplay {
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

        // One bound reference, so close() can remove exactly what loadHand() added
        this._onKeydown = this.handleKeydown.bind(this);
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
        document.addEventListener('keydown', this._onKeydown);

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
     * Render the current turn and wire up its controls
     */
    render() {
        this.container.innerHTML = renderReplay(this);
        this.attachEventListeners();
    }

    /**
     * Render error state
     */
    renderError(message) {
        this.container.innerHTML = renderError(message, this.options.onClose);
        this.attachEventListeners();
    }

    /**
     * Render no turns state
     */
    renderNoTurns() {
        this.container.innerHTML = renderNoTurns(this.options.onClose);
        this.attachEventListeners();
    }

    /**
     * Attach event listeners for controls and turn list
     */
    attachEventListeners() {
        // Navigation and close buttons
        this.container.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                switch (action) {
                    case 'first': this.firstTurn(); break;
                    case 'prev': this.prevTurn(); break;
                    case 'next': this.nextTurn(); break;
                    case 'last': this.lastTurn(); break;
                    case 'close': this.close(); break;
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
            document.removeEventListener('keydown', this._onKeydown);
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
