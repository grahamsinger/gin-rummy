// Gin Rummy Web UI

const API_BASE = '/api/game';

// Game state
let gameState = null;
let pendingDiscardCard = null;  // Card waiting for knock confirmation
let pendingMeldDiscardCard = null;  // Card waiting for meld confirmation
let sortMode = localStorage.getItem('sortMode') || 'value';  // 'suit', 'rank', or 'value'
let drawnCardId = null;  // ID of the card just drawn (for highlighting)

// Settings persistence
const savedSettings = {
    playerName: localStorage.getItem('playerName') || null,
    aiDifficulty: localStorage.getItem('aiDifficulty') || 'medium'
};

// DOM elements
const elements = {
    playerHand: document.getElementById('player-hand'),
    opponentHand: document.getElementById('opponent-hand'),
    opponentCardCount: document.getElementById('opponent-card-count'),
    lastAiMove: document.getElementById('last-ai-move'),
    discardTop: document.getElementById('discard-top'),
    discardPile: document.getElementById('discard-pile'),
    deck: document.getElementById('deck'),
    deckCount: document.getElementById('deck-count'),
    deadwood: document.getElementById('deadwood'),
    playerScore: document.getElementById('player-score'),
    opponentScore: document.getElementById('opponent-score'),
    knockCheckbox: document.getElementById('knock-checkbox'),
    statusMessage: document.getElementById('status-message'),
    newGameBtn: document.getElementById('new-game-btn'),
    assistMode: document.getElementById('assist-mode'),
    assistPanel: document.getElementById('assist-panel'),
    deadCards: document.getElementById('dead-cards'),
    opponentKnown: document.getElementById('opponent-known'),
    roundModal: document.getElementById('round-modal'),
    roundResultTitle: document.getElementById('round-result-title'),
    roundResultDetails: document.getElementById('round-result-details'),
    modalPlayerLabel: document.getElementById('modal-player-label'),
    modalPlayerHand: document.getElementById('modal-player-hand'),
    modalOpponentLabel: document.getElementById('modal-opponent-label'),
    modalOpponentHand: document.getElementById('modal-opponent-hand'),
    nextRoundBtn: document.getElementById('next-round-btn'),
    knockModal: document.getElementById('knock-modal'),
    knockModalText: document.getElementById('knock-modal-text'),
    knockYesBtn: document.getElementById('knock-yes-btn'),
    knockNoBtn: document.getElementById('knock-no-btn'),
    meldConfirmModal: document.getElementById('meld-confirm-modal'),
    meldConfirmText: document.getElementById('meld-confirm-text'),
    meldConfirmYesBtn: document.getElementById('meld-confirm-yes-btn'),
    meldConfirmNoBtn: document.getElementById('meld-confirm-no-btn'),
    sortSuitBtn: document.getElementById('sort-suit'),
    sortRankBtn: document.getElementById('sort-rank'),
    sortValueBtn: document.getElementById('sort-value'),
    cardTracker: document.getElementById('card-tracker'),
    settingsModal: document.getElementById('settings-modal'),
    settingsForm: document.getElementById('settings-form'),
    playerNameInput: document.getElementById('player-name'),
    aiDifficultySelect: document.getElementById('ai-difficulty'),
    viewStatsBtn: document.getElementById('view-stats-btn'),
    statsModal: document.getElementById('stats-modal'),
    statsContent: document.getElementById('stats-content'),
    statsCloseBtn: document.getElementById('stats-close-btn'),
};

// Suit symbols
const SUIT_SYMBOLS = {
    spades: '♠',
    hearts: '♥',
    diamonds: '♦',
    clubs: '♣',
};

// Suit order for sorting
const SUIT_ORDER = {
    spades: 0,
    hearts: 1,
    diamonds: 2,
    clubs: 3,
};

// Rank order for sorting
const RANK_ORDER = {
    'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13,
};

// Card deadwood value
function getCardValue(card) {
    if (card.rank === 'A') return 1;
    if (['J', 'Q', 'K'].includes(card.rank)) return 10;
    return parseInt(card.rank);
}

// Sort cards based on current sort mode
function sortCards(cards) {
    const sorted = [...cards];

    if (sortMode === 'suit') {
        // Sort by suit first, then by rank within suit
        sorted.sort((a, b) => {
            const suitDiff = SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
            if (suitDiff !== 0) return suitDiff;
            return RANK_ORDER[a.rank] - RANK_ORDER[b.rank];
        });
    } else if (sortMode === 'rank') {
        // Run-aware sorting: keep consecutive same-suit cards together
        // Group cards by rank
        const rankGroups = {};
        cards.forEach(card => {
            const rank = RANK_ORDER[card.rank];
            if (!rankGroups[rank]) rankGroups[rank] = [];
            rankGroups[rank].push(card);
        });

        // Build a map of suit -> ranks for looking ahead
        const suitRanks = {};
        cards.forEach(card => {
            const suit = card.suit;
            if (!suitRanks[suit]) suitRanks[suit] = new Set();
            suitRanks[suit].add(RANK_ORDER[card.rank]);
        });

        // Process ranks in order, placing cards to keep sequences together
        const sortedRanks = Object.keys(rankGroups).map(Number).sort((a, b) => a - b);
        const result = [];
        const placedSuits = new Map(); // Track last rank placed for each suit

        sortedRanks.forEach(rank => {
            const cardsInRank = rankGroups[rank];

            // Sort cards to keep same-suit sequences together
            cardsInRank.sort((a, b) => {
                const aExtendsBackward = placedSuits.has(a.suit) && placedSuits.get(a.suit) === rank - 1;
                const bExtendsBackward = placedSuits.has(b.suit) && placedSuits.get(b.suit) === rank - 1;
                const aExtendsForward = suitRanks[a.suit]?.has(rank + 1);
                const bExtendsForward = suitRanks[b.suit]?.has(rank + 1);

                // Priority 1: Cards that extend existing sequences (backward) come first
                if (aExtendsBackward && !bExtendsBackward) return -1;
                if (!aExtendsBackward && bExtendsBackward) return 1;

                // Priority 2: Cards that will continue into future sequences come last (next to their continuations)
                if (aExtendsForward && !bExtendsForward) return 1;
                if (!aExtendsForward && bExtendsForward) return -1;

                // Priority 3: If tied, use suit order
                return SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
            });

            // Add cards and update tracking
            cardsInRank.forEach(card => {
                result.push(card);
                placedSuits.set(card.suit, rank);
            });
        });

        return result;
    } else if (sortMode === 'value') {
        // Sort by deadwood value (highest first), then by suit
        sorted.sort((a, b) => {
            const valueDiff = getCardValue(b) - getCardValue(a);
            if (valueDiff !== 0) return valueDiff;
            return SUIT_ORDER[a.suit] - SUIT_ORDER[b.suit];
        });
    }

    return sorted;
}

// Create a card element
function createCardElement(card, faceDown = false) {
    const div = document.createElement('div');

    if (faceDown) {
        div.className = 'card card-back';
        return div;
    }

    if (!card) {
        div.className = 'card empty';
        return div;
    }

    div.className = `card ${card.suit}`;
    div.dataset.cardId = card.id;

    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = card.rank;

    const suit = document.createElement('span');
    suit.className = 'suit';
    suit.textContent = SUIT_SYMBOLS[card.suit];

    div.appendChild(rank);
    div.appendChild(suit);

    return div;
}

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
            if (drawnCardId && card.id === drawnCardId) {
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
        if (drawnCardId && card.id === drawnCardId) {
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
        if (gameState.discard_top) {
            elements.discardPile.classList.add('clickable');
        }
    }
}

// Render the full game state
function renderGameState(state) {
    gameState = state;

    // Scores - dynamically determine player names from scores object
    if (state.scores) {
        const playerNames = Object.keys(state.scores);
        if (playerNames.length === 2) {
            // Assume first player is human, second is computer
            const humanName = playerNames[0];
            const opponentName = playerNames[1];

            // Update header labels if they've changed (must do this BEFORE updating scores)
            const playerLabel = document.querySelector('.scores .score:first-child');
            const opponentLabel = document.querySelector('.scores .score:last-child');
            if (playerLabel && !playerLabel.textContent.startsWith(humanName)) {
                playerLabel.innerHTML = `${humanName}: <span id="player-score">${state.scores[humanName] || 0}</span>`;
                // Re-capture the element reference after innerHTML update
                elements.playerScore = document.getElementById('player-score');
            }
            if (opponentLabel && !opponentLabel.textContent.startsWith(opponentName)) {
                opponentLabel.innerHTML = `${opponentName}: <span id="opponent-score">${state.scores[opponentName] || 0}</span>`;
                // Re-capture the element reference after innerHTML update
                elements.opponentScore = document.getElementById('opponent-score');
            }

            // Now update the scores (using potentially refreshed element references)
            elements.playerScore.textContent = state.scores[humanName] || 0;
            elements.opponentScore.textContent = state.scores[opponentName] || 0;
        }
    }

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
    if (state.deadwood > 10) {
        elements.knockCheckbox.checked = false;
    }

    // Clickable states
    updateClickableStates(state.phase, state.your_turn);

    // Status message
    elements.statusMessage.textContent = state.message || '';
    elements.statusMessage.classList.remove('thinking');

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

        // Render card tracker grid
        renderCardTracker(state);
    } else {
        elements.assistPanel.classList.add('hidden');
    }

    // Update last AI move from state (for page refresh scenarios)
    if (state.ai_action) {
        updateLastAiMove(state.ai_action);
    }

    // Check for round over
    if (state.round_over) {
        showRoundResult(state.round_result);
    }
}

// API calls
async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE}${endpoint}`, options);
    const data = await response.json();

    if (!response.ok) {
        console.error('API error:', data);
        elements.statusMessage.textContent = data.error || 'An error occurred';
        return null;
    }

    return data;
}

async function newGame(settings = null) {
    elements.roundModal.classList.add('hidden');
    elements.settingsModal.classList.add('hidden');
    elements.lastAiMove.textContent = '';  // Clear last AI move
    elements.knockCheckbox.checked = false;  // Reset knock checkbox
    const state = await apiCall('/new', 'POST', settings);
    if (state) {
        renderGameState(state);
    }
}

function showSettingsModal() {
    // Populate form with saved settings
    elements.playerNameInput.value = savedSettings.playerName || '';
    elements.aiDifficultySelect.value = savedSettings.aiDifficulty;
    elements.settingsModal.classList.remove('hidden');
}

async function getState() {
    const state = await apiCall('/state');
    if (state) {
        renderGameState(state);
    }
}

async function drawCard(source) {
    // Store hand before drawing to find the new card
    const handBefore = gameState ? gameState.hand.map(c => c.id) : [];

    const state = await apiCall('/draw', 'POST', { source });
    if (state) {
        // Find which card was drawn by comparing hands
        if (source === 'discard' && gameState && gameState.discard_top) {
            // If drawing from discard, we know which card it is
            drawnCardId = gameState.discard_top.id;
        } else {
            // If drawing from deck, find the new card
            const handAfter = state.hand.map(c => c.id);
            const newCards = handAfter.filter(id => !handBefore.includes(id));
            if (newCards.length > 0) {
                drawnCardId = newCards[0];
            }
        }

        renderGameState(state);

        // If it's still our turn (discarding phase), wait for discard
        // If it's AI's turn, trigger AI turn
        if (!state.your_turn) {
            await doAiTurn();
        }
    }
}

async function discardCard(cardId, knock = null) {
    // If knock not explicitly set, use the checkbox state
    if (knock === null) {
        knock = elements.knockCheckbox.checked;
    }

    const state = await apiCall('/discard', 'POST', { card: cardId, knock: knock });
    if (state) {
        // Check if we need to ask about knocking (for gin auto-knock)
        if (state.needs_knock_decision) {
            // If gin (0 deadwood), automatically knock without confirmation
            if (state.post_discard_deadwood === 0) {
                await discardCard(state.discard_card, true);
                return;
            }

            // This shouldn't happen with the checkbox approach, but handle it anyway
            // by treating it as a regular discard
            knock = false;
            await discardCard(state.discard_card, knock);
            return;
        }

        // Clear drawn card highlight after discard
        drawnCardId = null;

        // Uncheck the knock checkbox after use
        elements.knockCheckbox.checked = false;

        renderGameState(state);

        // After discarding, it's AI's turn
        if (!state.your_turn && !state.round_over) {
            await doAiTurn();
        }
    }
}

async function knock() {
    const state = await apiCall('/knock', 'POST');
    if (state) {
        renderGameState(state);
    }
}

async function nextRound() {
    elements.roundModal.classList.add('hidden');
    elements.lastAiMove.textContent = '';  // Clear last AI move
    elements.knockCheckbox.checked = false;  // Reset knock checkbox
    const state = await apiCall('/new-round', 'POST');
    if (state) {
        renderGameState(state);

        // Check if AI goes first
        if (!state.your_turn) {
            await doAiTurn();
        }
    }
}

async function doAiTurn() {
    // Show thinking indicator
    elements.statusMessage.textContent = "Computer is thinking...";
    elements.statusMessage.classList.add('thinking');

    // Small delay to show AI is "thinking"
    await new Promise(resolve => setTimeout(resolve, 600));

    // Get updated state (AI turn is executed server-side)
    const state = await apiCall('/ai-turn', 'POST');
    if (state) {
        // Display AI actions sequentially if available
        if (state.ai_action) {
            await displayAiAction(state.ai_action, state);
        } else {
            renderGameState(state);
        }

        // If still AI's turn (shouldn't happen normally), continue
        if (!state.your_turn && !state.round_over) {
            await doAiTurn();
        }
    }
}

async function displayAiAction(action, state) {
    // First, show the draw action
    if (action.type === 'turn') {
        // Highlight discard pile if drawing from it
        if (action.draw_from === 'discard') {
            elements.discardPile.classList.add('highlight-pickup');
            elements.statusMessage.textContent = `Computer picked up ${action.drew_card} from discard pile`;
            elements.statusMessage.classList.remove('thinking');
            elements.statusMessage.classList.add('ai-pickup');
        } else {
            elements.statusMessage.textContent = "Computer drew from deck";
            elements.statusMessage.classList.remove('thinking');
            elements.statusMessage.classList.add('ai-draw');
        }

        // Wait to show the draw action
        await new Promise(resolve => setTimeout(resolve, 1000));

        // Remove highlight
        elements.discardPile.classList.remove('highlight-pickup');

        // Show the discard action
        elements.statusMessage.textContent = `Computer discarded ${action.discarded}`;
        elements.statusMessage.classList.remove('ai-pickup', 'ai-draw');
        elements.statusMessage.classList.add('ai-discard');

        // Update the UI with the new state
        renderGameState(state);

        // Wait to show the discard action
        await new Promise(resolve => setTimeout(resolve, 800));

        // Clear status classes
        elements.statusMessage.classList.remove('ai-discard');

        // Persist the last AI move summary
        updateLastAiMove(action);
    } else if (action.type === 'first_discard') {
        elements.statusMessage.textContent = `Computer discarded ${action.discarded}`;
        elements.statusMessage.classList.remove('thinking');
        renderGameState(state);
        await new Promise(resolve => setTimeout(resolve, 800));

        // Persist the last AI move summary
        updateLastAiMove(action);
    }
}

// Format card ID (e.g., "KD") to display format (e.g., "K♦")
function formatCardId(cardId) {
    if (!cardId) return cardId;
    const suitChar = cardId.slice(-1);
    const rank = cardId.slice(0, -1);
    const suitMap = { 'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣' };
    return rank + (suitMap[suitChar] || suitChar);
}

// Update the persistent last AI move display
function updateLastAiMove(action) {
    if (!action) {
        elements.lastAiMove.textContent = '';
        return;
    }

    let moveText = '';
    if (action.type === 'turn') {
        if (action.draw_from === 'discard') {
            moveText = `Last move: picked up ${formatCardId(action.drew_card)}, discarded ${formatCardId(action.discarded)}`;
        } else {
            moveText = `Last move: drew from deck, discarded ${formatCardId(action.discarded)}`;
        }
    } else if (action.type === 'first_discard') {
        moveText = `Last move: discarded ${formatCardId(action.discarded)}`;
    } else if (action.type === 'knock') {
        moveText = `Last move: knocked with ${formatCardId(action.discarded)}`;
    }

    elements.lastAiMove.textContent = moveText;
}

// Check if a card is part of a meld
function isCardInMeld(cardId) {
    if (!gameState || !gameState.melds) {
        return false;
    }
    return gameState.melds.some(meld => meld.cards.includes(cardId));
}

// Render card tracker grid (all 52 cards with status)
function renderCardTracker(state) {
    if (!state.assist) {
        elements.cardTracker.innerHTML = '';
        return;
    }

    elements.cardTracker.innerHTML = '';

    // Build sets for quick lookup
    const myHandIds = new Set(state.hand.map(c => c.id));
    const deadCardIds = new Set(state.assist.dead_cards.map(c => {
        // Convert "A♣" format to "AC" format for comparison
        return c.replace('♠', 'S').replace('♥', 'H').replace('♦', 'D').replace('♣', 'C');
    }));
    const opponentKnownIds = new Set(state.assist.opponent_known.map(c => {
        return c.replace('♠', 'S').replace('♥', 'H').replace('♦', 'D').replace('♣', 'C');
    }));
    const discardTopId = state.discard_top ? state.discard_top.id : null;

    // Card ranks and suits in order
    const ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
    const suits = [
        { name: 'spades', symbol: '♠' },
        { name: 'hearts', symbol: '♥' },
        { name: 'diamonds', symbol: '♦' },
        { name: 'clubs', symbol: '♣' }
    ];

    // Create grid: 13 rows (ranks) × 4 columns (suits)
    ranks.forEach(rank => {
        const rowDiv = document.createElement('div');
        rowDiv.className = 'tracker-row';

        suits.forEach(suit => {
            const cardId = `${rank}${suit.name[0].toUpperCase()}`;
            const cellDiv = document.createElement('div');
            cellDiv.className = 'tracker-cell';
            cellDiv.textContent = `${rank}${suit.symbol}`;

            // Color code based on location (prioritize opponent known over dead)
            if (myHandIds.has(cardId)) {
                cellDiv.classList.add('in-my-hand');
                cellDiv.title = 'In your hand';
            } else if (opponentKnownIds.has(cardId)) {
                cellDiv.classList.add('opponent-known');
                cellDiv.title = 'Opponent has this';
            } else if (discardTopId === cardId) {
                cellDiv.classList.add('discard-top');
                cellDiv.title = 'Available on discard pile';
            } else if (deadCardIds.has(cardId)) {
                cellDiv.classList.add('dead-card');
                cellDiv.title = 'Dead (buried in discard pile)';
            } else {
                cellDiv.classList.add('unknown');
                cellDiv.title = 'Unknown (in deck or opponent hand)';
            }

            // Red suits
            if (suit.name === 'hearts' || suit.name === 'diamonds') {
                cellDiv.classList.add('red-suit');
            }

            rowDiv.appendChild(cellDiv);
        });

        elements.cardTracker.appendChild(rowDiv);
    });
}

// Event handlers
function handleCardClick(card) {
    if (!gameState || !gameState.your_turn || gameState.phase !== 'discarding') {
        return;
    }

    // Check if card is in a meld - confirm before discarding
    if (isCardInMeld(card.id)) {
        pendingMeldDiscardCard = card.id;
        elements.meldConfirmText.textContent = `${card.rank}${SUIT_SYMBOLS[card.suit]} is part of a meld. Discard anyway?`;
        elements.meldConfirmModal.classList.remove('hidden');
        return;
    }

    // Single click to discard
    discardCard(card.id);
}

// Render a hand with melds grouped for the modal
function renderModalHand(container, handData) {
    container.innerHTML = '';

    if (!handData || !handData.cards) return;

    // Build set of melded card IDs and map to meld index
    const cardToMeld = new Map();
    if (handData.melds) {
        handData.melds.forEach((meld, idx) => {
            meld.cards.forEach(cardId => cardToMeld.set(cardId, idx));
        });
    }

    // Group cards by meld
    const meldGroups = new Map();
    const deadwoodCards = [];

    handData.cards.forEach(card => {
        if (cardToMeld.has(card.id)) {
            const meldIdx = cardToMeld.get(card.id);
            if (!meldGroups.has(meldIdx)) {
                meldGroups.set(meldIdx, []);
            }
            meldGroups.get(meldIdx).push(card);
        } else {
            deadwoodCards.push(card);
        }
    });

    // Render meld groups (sort cards within each meld by rank)
    meldGroups.forEach((cards) => {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'meld-group';

        // Sort cards by rank within meld (for runs to be in order)
        const sortedCards = [...cards].sort((a, b) => RANK_ORDER[a.rank] - RANK_ORDER[b.rank]);

        sortedCards.forEach(card => {
            const cardEl = createCardElement(card);
            cardEl.classList.add('melded');
            groupDiv.appendChild(cardEl);
        });
        container.appendChild(groupDiv);
    });

    // Render deadwood cards
    deadwoodCards.forEach(card => {
        container.appendChild(createCardElement(card));
    });

    // Add deadwood label
    const deadwoodLabel = document.createElement('div');
    deadwoodLabel.className = 'deadwood-label';
    deadwoodLabel.textContent = `Deadwood: ${handData.deadwood}`;
    container.appendChild(deadwoodLabel);
}

// Show round result modal
function showRoundResult(result) {
    if (!result) return;

    elements.roundResultTitle.textContent = result.is_draw ? 'Round Draw' : 'Round Over';

    // Get player names from game state scores
    const playerNames = gameState && gameState.scores ? Object.keys(gameState.scores) : ['You', 'Computer'];
    const humanName = playerNames[0] || 'You';
    const opponentName = playerNames[1] || 'Computer';
    const humanWon = result.winner === humanName;

    let details = '';
    if (result.is_draw) {
        details = 'Deck exhausted - no winner this round';
    } else if (humanWon) {
        if (result.is_gin) {
            details = `GIN! You win ${result.points} points!`;
        } else {
            details = `You win ${result.points} points!`;
        }
    } else {
        if (result.is_undercut) {
            details = `Undercut! ${opponentName} wins ${result.points} points!`;
        } else if (result.is_gin) {
            details = `${opponentName} gets GIN! Wins ${result.points} points!`;
        } else {
            details = `${opponentName} wins ${result.points} points`;
        }
    }

    // Add layoff information if cards were laid off
    if (result.layoff_cards && result.layoff_cards.length > 0) {
        const layoffCardsStr = result.layoff_cards.map(formatCardId).join(' ');
        const deadwoodAfter = result.defender_deadwood_before -
            result.layoff_cards.reduce((sum, card) => {
                // Calculate deadwood value from card id (e.g., "10H" -> 10, "KS" -> 10, "AS" -> 1)
                const rankPart = card.slice(0, -1);
                let value;
                if (rankPart === 'A') value = 1;
                else if (rankPart === 'J' || rankPart === 'Q' || rankPart === 'K') value = 10;
                else value = parseInt(rankPart);
                return sum + value;
            }, 0);

        // Determine who the defender is (opposite of winner in knock, same as winner in undercut)
        const defenderName = result.is_undercut ? result.winner :
            (humanWon ? opponentName : humanName);

        details += `\n\n${defenderName} laid off: ${layoffCardsStr}`;
        details += `\n(Deadwood: ${result.defender_deadwood_before} → ${deadwoodAfter})`;
    }

    elements.roundResultDetails.textContent = details;

    // Update modal labels with actual player names
    elements.modalPlayerLabel.textContent = `${humanName}'s Hand`;
    elements.modalOpponentLabel.textContent = `${opponentName}'s Hand`;

    // Render hands in modal with melds grouped
    renderModalHand(elements.modalPlayerHand, result.player_hand);
    renderModalHand(elements.modalOpponentHand, result.opponent_hand);

    elements.roundModal.classList.remove('hidden');
}

// Initialize event listeners
function init() {
    // Deck click
    elements.deck.addEventListener('click', () => {
        if (gameState && gameState.your_turn && gameState.phase === 'drawing') {
            drawCard('deck');
        }
    });

    // Discard pile click
    elements.discardPile.addEventListener('click', () => {
        if (gameState && gameState.your_turn && gameState.phase === 'drawing' && gameState.discard_top) {
            drawCard('discard');
        }
    });

    // Knock modal - Yes button
    elements.knockYesBtn.addEventListener('click', async () => {
        elements.knockModal.classList.add('hidden');
        if (pendingDiscardCard) {
            await discardCard(pendingDiscardCard, true);
            pendingDiscardCard = null;
        }
    });

    // Knock modal - No button
    elements.knockNoBtn.addEventListener('click', async () => {
        elements.knockModal.classList.add('hidden');
        if (pendingDiscardCard) {
            await discardCard(pendingDiscardCard, false);
            pendingDiscardCard = null;
        }
    });

    // Settings form submission
    elements.settingsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const playerName = elements.playerNameInput.value.trim() || null;
        const aiDifficulty = elements.aiDifficultySelect.value;

        // Save to localStorage
        if (playerName) {
            localStorage.setItem('playerName', playerName);
        } else {
            localStorage.removeItem('playerName');
        }
        localStorage.setItem('aiDifficulty', aiDifficulty);

        // Update savedSettings
        savedSettings.playerName = playerName;
        savedSettings.aiDifficulty = aiDifficulty;

        const settings = {
            player_name: playerName,
            ai_difficulty: aiDifficulty
        };
        newGame(settings);
    });

    // New game button
    elements.newGameBtn.addEventListener('click', showSettingsModal);

    // Next round button
    elements.nextRoundBtn.addEventListener('click', nextRound);

    // Assist mode toggle
    elements.assistMode.addEventListener('change', () => {
        if (gameState) {
            renderGameState(gameState);
        }
    });

    // Meld confirmation modal - Yes button
    elements.meldConfirmYesBtn.addEventListener('click', async () => {
        elements.meldConfirmModal.classList.add('hidden');
        if (pendingMeldDiscardCard) {
            await discardCard(pendingMeldDiscardCard);
            pendingMeldDiscardCard = null;
        }
    });

    // Meld confirmation modal - No button
    elements.meldConfirmNoBtn.addEventListener('click', () => {
        elements.meldConfirmModal.classList.add('hidden');
        pendingMeldDiscardCard = null;
        // User can now click another card
    });

    // Sort buttons
    elements.sortSuitBtn.addEventListener('click', () => setSortMode('suit'));
    elements.sortRankBtn.addEventListener('click', () => setSortMode('rank'));
    elements.sortValueBtn.addEventListener('click', () => setSortMode('value'));

    // Stats button and modal
    elements.viewStatsBtn.addEventListener('click', showPlayerStats);
    elements.statsCloseBtn.addEventListener('click', () => {
        elements.statsModal.classList.add('hidden');
    });

    // Initialize sort button active state
    updateSortButtonStates();

    // Auto-start game with saved settings
    const settings = {
        player_name: savedSettings.playerName,
        ai_difficulty: savedSettings.aiDifficulty
    };
    newGame(settings);
}

// Set sort mode and re-render
function setSortMode(mode) {
    sortMode = mode;
    localStorage.setItem('sortMode', mode);
    updateSortButtonStates();
    if (gameState) {
        renderGameState(gameState);
    }
}

// Update active state of sort buttons
function updateSortButtonStates() {
    elements.sortSuitBtn.classList.toggle('active', sortMode === 'suit');
    elements.sortRankBtn.classList.toggle('active', sortMode === 'rank');
    elements.sortValueBtn.classList.toggle('active', sortMode === 'value');
}

// Fetch and display player stats
async function showPlayerStats() {
    const playerName = savedSettings.playerName || 'You';
    elements.statsModal.classList.remove('hidden');
    elements.statsContent.innerHTML = '<div class="stats-loading">Loading stats...</div>';

    try {
        const response = await fetch(`/api/stats/${encodeURIComponent(playerName)}`);
        const stats = await response.json();

        if (stats.total_hands === 0) {
            elements.statsContent.innerHTML = `
                <div class="stats-empty">
                    <p>No statistics available yet for <strong>${playerName}</strong>.</p>
                    <p>Play some hands to start tracking your stats!</p>
                </div>
            `;
            return;
        }

        // Render stats
        const html = `
            <div class="stats-player-name">
                <h3>${playerName}</h3>
            </div>
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
                    <span class="stat-label">Knock Aggression</span>
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

// Start the game when page loads
document.addEventListener('DOMContentLoaded', init);
