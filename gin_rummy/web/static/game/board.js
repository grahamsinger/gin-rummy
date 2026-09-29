// Rendering the table: hands, discard pile, clickable states, and the full game state.
import { escapeHtml as esc } from '../card-utils.js';
import { discardCard } from './actions.js';
import { updateLastAiMove } from './ai-playback.js';
import { renderCardTracker, renderHelpfulCards } from './assist.js';
import { RANK_ORDER, SUIT_SYMBOLS, createCardElement, isCardInMeld, sortCards } from './cards.js';
import { elements } from './dom.js';
import { showRoundResult } from './modals.js';
import { ui, savedSettings } from './state.js';

// Render opponent's hand (face down)
function renderOpponentHand(count) {
    elements.opponentHand.innerHTML = '';
    elements.opponentCardCount.textContent = count;

    for (let i = 0; i < count; i++) {
        elements.opponentHand.appendChild(createCardElement(null, true));
    }
}

// Render player's hand with melds grouped
function renderPlayerHand(hand, melds, phase) {
    elements.playerHand.innerHTML = '';

    // Build a set of melded card IDs
    const meldedCards = new Set();
    const cardToMeld = new Map();

    if (melds) {
        melds.forEach((meld, meldIdx) => {
            meld.cards.forEach(cardId => {
                meldedCards.add(cardId);
                cardToMeld.set(cardId, meldIdx);
            });
        });
    }

    // Group cards by meld
    const meldGroups = new Map();
    const ungroupedCards = [];

    hand.forEach(card => {
        if (cardToMeld.has(card.id)) {
            const meldIdx = cardToMeld.get(card.id);
            if (!meldGroups.has(meldIdx)) {
                meldGroups.set(meldIdx, []);
            }
            meldGroups.get(meldIdx).push(card);
        } else {
            ungroupedCards.push(card);
        }
    });

    // Render meld groups first (sort cards within each meld by rank)
    meldGroups.forEach((cards, meldIdx) => {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'meld-group';

        // Sort cards by rank within meld (for runs to be in order)
        const sortedCards = [...cards].sort((a, b) => RANK_ORDER[a.rank] - RANK_ORDER[b.rank]);

        sortedCards.forEach(card => {
            const cardEl = createCardElement(card);
            cardEl.classList.add('melded');

            // Highlight the card that was just drawn (even if it's in a meld)
            if (ui.drawnCardId && card.id === ui.drawnCardId) {
                cardEl.classList.add('drawn-card');
            }

            if (phase === 'discarding') {
                cardEl.classList.add('clickable');
                cardEl.addEventListener('click', () => handleCardClick(card));
            }
            groupDiv.appendChild(cardEl);
        });

        elements.playerHand.appendChild(groupDiv);
    });

    // Sort and render ungrouped (deadwood) cards
    const sortedDeadwood = sortCards(ungroupedCards);
    sortedDeadwood.forEach(card => {
        const cardEl = createCardElement(card);

        // Highlight the card that was just drawn
        if (ui.drawnCardId && card.id === ui.drawnCardId) {
            cardEl.classList.add('drawn-card');
        }

        if (phase === 'discarding') {
            cardEl.classList.add('clickable');
            cardEl.addEventListener('click', () => handleCardClick(card));
        }
        elements.playerHand.appendChild(cardEl);
    });
}

// Render discard pile top card
function renderDiscardTop(card) {
    elements.discardTop.innerHTML = '';

    if (card) {
        const cardEl = createCardElement(card);
        elements.discardTop.className = `card ${card.suit}`;
        elements.discardTop.appendChild(cardEl.querySelector('.rank').cloneNode(true));
        elements.discardTop.appendChild(cardEl.querySelector('.suit').cloneNode(true));
    } else {
        elements.discardTop.className = 'card empty';
    }
}

// Update clickable states based on phase
function updateClickableStates(phase, yourTurn) {
    // Reset all clickable states
    elements.deck.classList.remove('clickable');
    elements.discardPile.classList.remove('clickable');

    if (!yourTurn) return;

    if (phase === 'drawing') {
        elements.deck.classList.add('clickable');
        if (ui.gameState.discard_top) {
            elements.discardPile.classList.add('clickable');
        }
    }
}

// Render the full game state
export function renderGameState(state) {
    ui.gameState = state;

    // Update player name in header dynamically
    const playerName = state.player_name || savedSettings.playerName || 'Player';
    if (elements.playerNameDisplay) {
        elements.playerNameDisplay.textContent = playerName;
    }

    // Scores - dynamically determine player names from scores object
    if (state.scores) {
        const playerNames = Object.keys(state.scores);
        if (playerNames.length === 2) {
            // Assume first player is human, second is computer
            const humanName = playerNames[0];
            const opponentName = playerNames[1];
            const humanScore = state.scores[humanName] || 0;
            const opponentScore = state.scores[opponentName] || 0;

            // Format scores with target if in target mode
            const formatScore = (score) => {
                if (state.game_mode === 'target' && state.target_score) {
                    return `${score} / ${state.target_score}`;
                }
                return score;
            };

            // Update header labels if they've changed (must do this BEFORE updating scores)
            const playerLabel = document.querySelector('.scores .score:first-child');
            const opponentLabel = document.querySelector('.scores .score:last-child');
            if (playerLabel && !playerLabel.textContent.startsWith(humanName)) {
                playerLabel.innerHTML = `${esc(humanName)}: <span id="player-score">${formatScore(humanScore)}</span>`;
                // Re-capture the element reference after innerHTML update
                elements.playerScore = document.getElementById('player-score');
            }
            const diffLabel = state.ai_difficulty ? ` (${state.ai_difficulty.charAt(0).toUpperCase() + state.ai_difficulty.slice(1)})` : '';
            if (opponentLabel && !opponentLabel.textContent.startsWith(opponentName)) {
                opponentLabel.innerHTML = `${esc(opponentName)}${diffLabel}: <span id="opponent-score">${formatScore(opponentScore)}</span>`;
                // Re-capture the element reference after innerHTML update
                elements.opponentScore = document.getElementById('opponent-score');
            }

            // Now update the scores (using potentially refreshed element references)
            elements.playerScore.textContent = formatScore(humanScore);
            elements.opponentScore.textContent = formatScore(opponentScore);
        }
    }

    // AI difficulty labels
    if (state.ai_difficulty) {
        const label = state.ai_difficulty.charAt(0).toUpperCase() + state.ai_difficulty.slice(1);
        if (elements.aiDifficultyDisplay) elements.aiDifficultyDisplay.textContent = label;
        if (elements.aiDifficultyLabel) elements.aiDifficultyLabel.textContent = `[${label}] `;
    }

    // Note: Don't check for game over here - let round result modal show first
    // The "Next Round" button will handle showing the game over modal

    // Deck
    elements.deckCount.textContent = state.deck_remaining;

    // Discard pile
    renderDiscardTop(state.discard_top);

    // Opponent's hand
    renderOpponentHand(state.opponent_card_count);

    // Player's hand
    renderPlayerHand(state.hand, state.melds, state.your_turn ? state.phase : null);

    // Deadwood
    elements.deadwood.textContent = state.deadwood;

    // Disable knock checkbox if not in discarding phase or not your turn
    elements.knockCheckbox.disabled = !(state.your_turn && state.phase === 'discarding');

    // Auto-uncheck if deadwood is too high to knock
    // (threshold is dynamic in Oklahoma Gin, not always 10)
    const knockThreshold = state.knock_threshold ?? 10;
    if (state.deadwood > knockThreshold) {
        elements.knockCheckbox.checked = false;
    }

    // Clickable states
    updateClickableStates(state.phase, state.your_turn);

    // Status message
    elements.playerStatus.textContent = state.message || '';

    // Assist info
    if (elements.assistMode.checked && state.assist) {
        elements.assistPanel.classList.remove('hidden');

        // Dead cards with tooltip
        elements.deadCards.textContent = `Dead cards: ${state.assist.dead_cards.length}`;
        if (state.assist.dead_cards.length > 0) {
            elements.deadCards.textContent += ` (${state.assist.dead_cards.join(', ')})`;
        }
        elements.deadCards.title = "Cards in the discard pile that are buried (can't be drawn)";

        // Opponent known cards with tooltip
        elements.opponentKnown.textContent = `Opponent known: ${state.assist.opponent_known.length}`;
        if (state.assist.opponent_known.length > 0) {
            elements.opponentKnown.textContent += ` (${state.assist.opponent_known.join(', ')})`;
        }
        elements.opponentKnown.title = "Cards in opponent's hand that you've seen (picked from discard minus cards they re-discarded)";

        // Helpful cards ranking
        renderHelpfulCards(state.assist.helpfulness);

        // Render card tracker grid
        renderCardTracker(state);
    } else {
        elements.assistPanel.classList.add('hidden');
    }

    // Update last AI move from state (for page refresh scenarios)
    if (state.ai_action) {
        updateLastAiMove(state.ai_action);
    }

    // Display game format info
    const formatParts = [];
    if (state.oklahoma_gin) {
        formatParts.push('Oklahoma Gin');
    }
    if (state.match_mode) {
        formatParts.push('Best of 3');
    } else if (state.game_mode === 'target' && state.target_score) {
        formatParts.push(`First to ${state.target_score}`);
    }
    elements.gameFormatDisplay.textContent = formatParts.length > 0 ? formatParts.join(' • ') : '';

    // Display Oklahoma Gin info
    if (state.oklahoma_gin) {
        elements.knockThresholdDisplay.classList.remove('hidden');
        elements.knockThresholdValue.textContent = state.knock_threshold;

        // Show spade doubling indicator if applicable
        if (state.upcard && state.spade_doubling && state.upcard.suit === 'spades') {
            elements.spadeIndicator.classList.remove('hidden');
        } else {
            elements.spadeIndicator.classList.add('hidden');
        }
    } else {
        elements.knockThresholdDisplay.classList.add('hidden');
        elements.spadeIndicator.classList.add('hidden');
    }

    // Display match progress
    if (state.match_mode && state.games_won) {
        elements.matchProgress.classList.remove('hidden');
        const playerGames = state.games_won[state.player_name] || 0;
        const aiGames = state.games_won['Computer'] || 0;
        const playerDisplayName = state.player_name || savedSettings.playerName || 'Player';
        elements.gamesWonDisplay.textContent = `${playerDisplayName} ${playerGames} - ${aiGames} Computer`;
    } else {
        elements.matchProgress.classList.add('hidden');
    }

    // Check for round over
    if (state.round_over) {
        showRoundResult(state.round_result);
    }
}

// Event handlers
function handleCardClick(card) {
    if (!ui.gameState || !ui.gameState.your_turn || ui.gameState.phase !== 'discarding') {
        return;
    }

    // Check if card is in a meld - confirm before discarding
    if (isCardInMeld(card.id)) {
        ui.pendingMeldDiscardCard = card.id;
        elements.meldConfirmText.textContent = `${card.rank}${SUIT_SYMBOLS[card.suit]} is part of a meld. Discard anyway?`;
        elements.meldConfirmModal.classList.remove('hidden');
        return;
    }

    // Single click to discard
    discardCard(card.id);
}
