// Gin Rummy Web UI

const API_BASE = '/api/game';

// Game state
let gameState = null;
let pendingDiscardCard = null;  // Card waiting for knock confirmation
let pendingMeldDiscardCard = null;  // Card waiting for meld confirmation
let sortMode = localStorage.getItem('sortMode') || 'value';  // 'suit', 'rank', or 'value'
let drawnCardId = null;  // ID of the card just drawn (for highlighting)

// Generate a random player name like "Guest_a3f7"
function generatePlayerName() {
    const suffix = Math.random().toString(16).substring(2, 6);
    return `Guest_${suffix}`;
}

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
    playerStatus: document.getElementById('player-status'),
    playerNameDisplay: document.getElementById('player-name-display'),
    playerScore: document.getElementById('player-score'),
    opponentScore: document.getElementById('opponent-score'),
    aiDifficultyDisplay: document.getElementById('ai-difficulty-display'),
    aiDifficultyLabel: document.getElementById('ai-difficulty-label'),
    knockCheckbox: document.getElementById('knock-checkbox'),
    newGameBtn: document.getElementById('new-game-btn'),
    assistMode: document.getElementById('assist-mode'),
    assistPanel: document.getElementById('assist-panel'),
    deadCards: document.getElementById('dead-cards'),
    opponentKnown: document.getElementById('opponent-known'),
    helpfulCards: document.getElementById('helpful-cards'),
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
    playerNamesList: document.getElementById('player-names-list'),
    cancelSettingsBtn: document.getElementById('cancel-settings-btn'),
    aiDifficultySelect: document.getElementById('ai-difficulty'),
    gameModeSelect: document.getElementById('game-mode'),
    targetScoreSelect: document.getElementById('target-score'),
    targetScoreField: document.getElementById('target-score-field'),
    gameOverModal: document.getElementById('game-over-modal'),
    changeSettingsAfterWinBtn: document.getElementById('change-settings-after-win-btn'),
    gameOverTitle: document.getElementById('game-over-title'),
    gameOverDetails: document.getElementById('game-over-details'),
    newGameAfterWinBtn: document.getElementById('new-game-after-win-btn'),
    viewStatsAfterWinBtn: document.getElementById('view-stats-after-win-btn'),
    viewStatsBtn: document.getElementById('view-stats-btn'),
    statsModal: document.getElementById('stats-modal'),
    statsContent: document.getElementById('stats-content'),
    statsCloseBtn: document.getElementById('stats-close-btn'),
    statsPlayerSelect: document.getElementById('stats-player-select'),
    clearStatsBtn: document.getElementById('clear-stats-btn'),
    clearStatsModal: document.getElementById('clear-stats-modal'),
    clearStatsPlayerName: document.getElementById('clear-stats-player-name'),
    clearStatsConfirmBtn: document.getElementById('clear-stats-confirm-btn'),
    clearStatsCancelBtn: document.getElementById('clear-stats-cancel-btn'),
    scoreHistoryBtn: document.getElementById('score-history-btn'),
    scoreHistoryModal: document.getElementById('score-history-modal'),
    scoreHistoryContent: document.getElementById('score-history-content'),
    scoreHistoryCloseBtn: document.getElementById('score-history-close-btn'),
    replayModal: document.getElementById('replay-modal'),
    replayContainer: document.getElementById('replay-container'),
    oklahomaGinCheckbox: document.getElementById('oklahoma-gin'),
    spadeDoublingCheckbox: document.getElementById('spade-doubling'),
    spadeDoublingField: document.getElementById('spade-doubling-field'),
    matchModeCheckbox: document.getElementById('match-mode'),
    knockThresholdDisplay: document.getElementById('knock-threshold-display'),
    knockThresholdValue: document.getElementById('knock-threshold-value'),
    spadeIndicator: document.getElementById('spade-indicator'),
    matchProgress: document.getElementById('match-progress'),
    gamesWonDisplay: document.getElementById('games-won-display'),
    gameFormatDisplay: document.getElementById('game-format-display'),
    resumeModal: document.getElementById('resume-modal'),
    resumeGameDetails: document.getElementById('resume-game-details'),
    resumeYesBtn: document.getElementById('resume-yes-btn'),
    resumeNoBtn: document.getElementById('resume-no-btn'),
    miniGamesBtn: document.getElementById('mini-games-btn'),
    miniGamesModal: document.getElementById('mini-games-modal'),
    miniGamesCloseBtn: document.getElementById('mini-games-close-btn'),
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
                playerLabel.innerHTML = `${humanName}: <span id="player-score">${formatScore(humanScore)}</span>`;
                // Re-capture the element reference after innerHTML update
                elements.playerScore = document.getElementById('player-score');
            }
            const diffLabel = state.ai_difficulty ? ` (${state.ai_difficulty.charAt(0).toUpperCase() + state.ai_difficulty.slice(1)})` : '';
            if (opponentLabel && !opponentLabel.textContent.startsWith(opponentName)) {
                opponentLabel.innerHTML = `${opponentName}${diffLabel}: <span id="opponent-score">${formatScore(opponentScore)}</span>`;
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
    if (state.deadwood > 10) {
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
        elements.playerStatus.textContent = data.error || 'An error occurred';
        return null;
    }

    return data;
}

async function newGame(settings = null) {
    elements.roundModal.classList.add('hidden');
    elements.settingsModal.classList.add('hidden');
    elements.lastAiMove.textContent = '';  // Clear last AI move
    renderMcThinking(null);  // Clear thinking panel
    elements.knockCheckbox.checked = false;  // Reset knock checkbox
    const state = await apiCall('/new', 'POST', settings);
    if (state) {
        renderGameState(state);

        // Check if AI goes first (e.g., in Oklahoma mode when computer is non-dealer)
        if (!state.your_turn) {
            await doAiTurn();
        }
    }
}

async function showSettingsModal() {
    // Load existing players for autocomplete
    await loadPlayerNamesForSettings();

    // Clear player name initially to show all options in datalist
    // User can then select from list or type a new name
    elements.playerNameInput.value = '';
    elements.playerNameInput.placeholder = savedSettings.playerName || 'Enter name...';
    elements.aiDifficultySelect.value = savedSettings.aiDifficulty;

    // Load saved game mode settings
    const savedGameMode = localStorage.getItem('gameMode') || 'target';
    const savedTargetScore = localStorage.getItem('targetScore') || '100';
    elements.gameModeSelect.value = savedGameMode;
    elements.targetScoreSelect.value = savedTargetScore;

    // Show/hide target score field based on mode
    if (savedGameMode === 'target') {
        elements.targetScoreField.style.display = 'flex';
    } else {
        elements.targetScoreField.style.display = 'none';
    }

    // Load Oklahoma Gin settings
    const oklahomaGin = localStorage.getItem('oklahomaGin') === 'true';
    const spadeDoubling = localStorage.getItem('spadeDoubling') !== 'false'; // default true
    const matchMode = localStorage.getItem('matchMode') === 'true';
    elements.oklahomaGinCheckbox.checked = oklahomaGin;
    elements.spadeDoublingCheckbox.checked = spadeDoubling;
    elements.matchModeCheckbox.checked = matchMode;

    // Show spade doubling field if Oklahoma is checked
    elements.spadeDoublingField.style.display = oklahomaGin ? 'flex' : 'none';

    elements.settingsModal.classList.remove('hidden');

    // Focus on player name input
    setTimeout(() => elements.playerNameInput.focus(), 100);
}

async function loadPlayerNamesForSettings() {
    try {
        const response = await fetch('/api/players');
        const players = await response.json();

        // Populate datalist with all players EXCEPT "Computer"
        elements.playerNamesList.innerHTML = players
            .filter(p => p.name !== 'Computer')
            .map(p =>
                `<option value="${p.name}">${p.name} (${p.total_hands} hands, ${(p.win_rate * 100).toFixed(0)}% wins)</option>`
            ).join('');
    } catch (error) {
        console.error('Failed to load player names:', error);
        // Silently fail - user can still type a name
    }
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
    // If knock not explicitly set, only use checkbox if it's checked
    // Otherwise pass null to let backend handle automatic gin detection
    if (knock === null) {
        knock = elements.knockCheckbox.checked ? true : null;
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

    // Check if game is over before starting new round
    if (gameState && gameState.game_over && gameState.game_winner) {
        showGameOver(gameState.game_winner, gameState.scores, gameState.target_score, gameState.match_mode, gameState.games_won, gameState.match_winner);
        return;
    }

    elements.lastAiMove.textContent = '';  // Clear last AI move
    renderMcThinking(null);  // Clear thinking panel
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
    elements.lastAiMove.textContent = "Computer is thinking...";
    elements.lastAiMove.classList.add('thinking');

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
            elements.lastAiMove.textContent = `Computer picked up ${formatCardId(action.drew_card)} from discard pile`;
            elements.lastAiMove.classList.remove('thinking');
            elements.lastAiMove.classList.add('ai-pickup');
        } else {
            elements.lastAiMove.textContent = "Computer drew from deck";
            elements.lastAiMove.classList.remove('thinking');
            elements.lastAiMove.classList.add('ai-draw');
        }

        // Wait to show the draw action
        await new Promise(resolve => setTimeout(resolve, 400));

        // Remove highlight
        elements.discardPile.classList.remove('highlight-pickup');

        // Show the discard action
        elements.lastAiMove.textContent = `Computer discarded ${formatCardId(action.discarded)}`;
        elements.lastAiMove.classList.remove('thinking', 'ai-pickup', 'ai-draw');
        elements.lastAiMove.classList.add('ai-discard');

        // Update the UI with the new state
        renderGameState(state);

        // Wait to show the discard action
        await new Promise(resolve => setTimeout(resolve, 300));

        // Clear status classes, then show persistent summary
        elements.lastAiMove.classList.remove('ai-discard');
        updateLastAiMove(action);
    } else if (action.type === 'first_discard') {
        elements.lastAiMove.textContent = `Computer discarded ${formatCardId(action.discarded)}`;
        elements.lastAiMove.classList.remove('thinking');
        renderGameState(state);
        await new Promise(resolve => setTimeout(resolve, 300));

        updateLastAiMove(action);
    }
}

// Format card ID (e.g., "KD") to display format (e.g., "K♦")
// Also handles cards already in symbol format (e.g., "K♦", "10♥")
function formatCardId(cardId) {
    if (!cardId) return cardId;
    // Already has suit symbol - return as-is
    if (/[♠♥♦♣]$/.test(cardId)) return cardId;
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
    elements.lastAiMove.classList.remove('thinking', 'ai-pickup', 'ai-draw', 'ai-discard');

    // Show MC thinking panel if data is available
    renderMcThinking(action ? action.mc_thinking : null);
}

// Toggle AI thinking panel expand/collapse
function toggleThinking() {
    const content = document.getElementById('ai-thinking-content');
    const arrow = document.getElementById('ai-thinking-arrow');
    content.classList.toggle('expanded');
    arrow.classList.toggle('expanded');
}

// Set up thinking panel toggle
(function() {
    const toggle = document.getElementById('ai-thinking-toggle');
    if (toggle) {
        toggle.addEventListener('click', toggleThinking);
    }
})();

// Render Monte Carlo thinking data
function renderMcThinking(mcThinking) {
    const panel = document.getElementById('ai-thinking-panel');
    const content = document.getElementById('ai-thinking-content');

    if (!mcThinking) {
        panel.style.display = 'none';
        content.innerHTML = '';
        return;
    }

    panel.style.display = '';
    let html = '';

    // Draw section
    if (mcThinking.draw) {
        const d = mcThinking.draw;
        const deckClass = d.choice === 'deck' ? 'mc-chosen' : 'mc-option';
        const discardClass = d.choice === 'discard' ? 'mc-chosen' : 'mc-option';
        const discardLabel = d.discard_card ? `DISCARD ${formatCardId(d.discard_card)}` : 'DISCARD';
        html += `<div class="mc-section">`;
        html += `<div class="mc-label">Draw</div>`;
        html += `<span class="${deckClass}">DECK: ${d.deck_avg_points > 0 ? '+' : ''}${d.deck_avg_points} avg</span>`;
        html += ` vs `;
        html += `<span class="${discardClass}">${discardLabel}: ${d.discard_avg_points > 0 ? '+' : ''}${d.discard_avg_points} avg</span>`;
        html += ` <span style="color:#78909c">(${d.deck_sims} sims each)</span>`;
        html += `</div>`;
    }

    // Discard section
    if (mcThinking.discard) {
        const disc = mcThinking.discard;
        html += `<div class="mc-section">`;
        html += `<div class="mc-label">Discard (${disc.deadwood_count} deadwood cards evaluated)</div>`;
        html += `<table class="mc-candidate-table">`;
        html += `<tr><th>Card</th><th>Avg Pts</th><th>Deadwood</th></tr>`;
        for (const cand of disc.candidates) {
            const isChosen = cand.card === disc.chosen;
            const rowClass = isChosen ? ' class="mc-row-chosen"' : '';
            const marker = isChosen ? ' ←' : '';
            html += `<tr${rowClass}>`;
            html += `<td>${formatCardId(cand.card)}${marker}</td>`;
            html += `<td>${cand.avg_points > 0 ? '+' : ''}${cand.avg_points}</td>`;
            html += `<td>${cand.deadwood_after}</td>`;
            html += `</tr>`;
        }
        html += `</table>`;
        if (disc.fallback) {
            html += `<div style="color:#ffb74d; margin-top:4px; font-size:0.9em">⚠ MC gap &lt; ${disc.min_advantage} threshold — fell back to heuristic</div>`;
        }
        html += `</div>`;
    }

    // Knock section
    if (mcThinking.knock) {
        const k = mcThinking.knock;
        html += `<div class="mc-section">`;
        html += `<div class="mc-label">Knock (deadwood: ${k.deadwood})</div>`;
        if (k.reason) {
            html += `<span class="mc-chosen">${k.reason === 'gin' ? 'GIN!' : k.reason.replace(/_/g, ' ')}</span>`;
        } else if (k.knock_avg_points !== null) {
            const knockClass = k.chose_knock ? 'mc-chosen' : 'mc-option';
            const contClass = !k.chose_knock ? 'mc-chosen' : 'mc-option';
            html += `<span class="${knockClass}">Knock: ${k.knock_avg_points > 0 ? '+' : ''}${k.knock_avg_points} avg</span>`;
            html += ` vs `;
            html += `<span class="${contClass}">Continue: ${k.continue_avg_points > 0 ? '+' : ''}${k.continue_avg_points} avg</span>`;
            html += ` → <span class="mc-chosen">${k.chose_knock ? 'Knocked' : 'Continued'}</span>`;
        }
        html += `</div>`;
    }

    content.innerHTML = html;
}

// Check if a card is part of a meld
function isCardInMeld(cardId) {
    if (!gameState || !gameState.melds) {
        return false;
    }
    return gameState.melds.some(meld => meld.cards.includes(cardId));
}

// Render helpful cards ranking
function renderHelpfulCards(helpfulness) {
    if (!helpfulness) {
        elements.helpfulCards.innerHTML = '';
        return;
    }

    const { helpful_cards, total_helpful, live_helpful } = helpfulness;

    // Build summary text
    let summaryText = `Helpful cards: ${live_helpful} live`;
    if (total_helpful > live_helpful) {
        summaryText += ` (${total_helpful - live_helpful} dead)`;
    }

    // Build list of top helpful cards (show top 10)
    const topCards = helpful_cards.slice(0, 10);
    let cardsHTML = '';
    if (topCards.length > 0) {
        cardsHTML = '<div class="helpful-cards-list">';
        topCards.forEach(cardInfo => {
            let cardClass = 'helpful-card';
            if (cardInfo.is_dead) {
                cardClass += ' dead';
            }
            if (cardInfo.completes_meld) {
                cardClass += ' meld-completing';
            }
            const tooltip = cardInfo.completes_meld
                ? `Completes a meld! Reduces deadwood by ${cardInfo.reduction}`
                : `Reduces deadwood by ${cardInfo.reduction}`;
            cardsHTML += `<span class="${cardClass}" title="${tooltip}">${cardInfo.card} (-${cardInfo.reduction})</span>`;
        });
        cardsHTML += '</div>';
    }

    elements.helpfulCards.innerHTML = `
        <div class="helpful-cards-summary">${summaryText}</div>
        ${cardsHTML}
    `;
    elements.helpfulCards.title = "Cards that would reduce your deadwood if added to your hand";
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
// deadwoodAfterLayoff: if provided, shows "before → after" transition for layoff
function renderModalHand(container, handData, deadwoodAfterLayoff) {
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

    // Render deadwood cards (sorted by rank)
    const sortedDeadwood = [...deadwoodCards].sort((a, b) => RANK_ORDER[a.rank] - RANK_ORDER[b.rank]);
    sortedDeadwood.forEach(card => {
        container.appendChild(createCardElement(card));
    });

    // Add deadwood label
    const deadwoodLabel = document.createElement('div');
    deadwoodLabel.className = 'deadwood-label';
    if (deadwoodAfterLayoff !== undefined && deadwoodAfterLayoff !== handData.deadwood) {
        deadwoodLabel.innerHTML =
            `Deadwood: ${handData.deadwood} → <span class="deadwood-after-layoff">${deadwoodAfterLayoff}</span>`;
    } else {
        deadwoodLabel.textContent = `Deadwood: ${handData.deadwood}`;
    }
    container.appendChild(deadwoodLabel);
}

// Show round result modal
function showRoundResult(result) {
    if (!result) return;

    // Detect game/match end scenarios
    const isGameOver = gameState && gameState.game_over && gameState.game_winner;
    const isMatchMode = gameState && gameState.match_mode;
    const isMatchOver = isMatchMode && gameState.match_winner;

    // Set modal title based on scenario
    if (result.is_draw) {
        elements.roundResultTitle.textContent = 'Round Draw';
    } else if (isMatchOver) {
        elements.roundResultTitle.textContent = 'Match Over - Round Results';
    } else if (isGameOver) {
        elements.roundResultTitle.textContent = 'Game Over - Round Results';
    } else {
        elements.roundResultTitle.textContent = 'Round Over';
    }

    // Get player names from game state scores
    const playerNames = gameState && gameState.scores ? Object.keys(gameState.scores) : [];
    const humanName = playerNames[0] || savedSettings.playerName || 'Player';
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

    // Compute layoff info (used in details text and hand deadwood display)
    let defenderIsHuman = false;
    let defenderDeadwoodAfter = undefined;
    if (result.layoff_cards && result.layoff_cards.length > 0) {
        const layoffCardsStr = result.layoff_cards.map(formatCardId).join(' ');
        defenderDeadwoodAfter = result.defender_deadwood_before -
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
        defenderIsHuman = defenderName === humanName;

        details += `\n\n${defenderName} laid off: ${layoffCardsStr}`;
        details += `\n(Deadwood: ${result.defender_deadwood_before} → ${defenderDeadwoodAfter})`;
    }

    // Add computer's final action if available (helps understand what happened)
    if (gameState && gameState.ai_action && !humanWon && !result.is_draw) {
        const action = gameState.ai_action;
        details += '\n\n';
        if (action.draw_from === 'discard' && action.drew_card) {
            details += `${opponentName} drew ${formatCardId(action.drew_card)} from discard pile`;
        } else {
            details += `${opponentName} drew from deck`;
        }
        details += ` and discarded ${formatCardId(action.discarded)}`;
    }

    // Add cumulative score display
    if (gameState && gameState.scores) {
        const humanScore = gameState.scores[humanName] || 0;
        const opponentScore = gameState.scores[opponentName] || 0;
        const targetInfo = gameState.target_score ? ` / ${gameState.target_score}` : '';
        details += `\n\nScore: ${humanName} ${humanScore}${targetInfo} - ${opponentName} ${opponentScore}${targetInfo}`;
    }

    // Append game/match winner info
    if (isMatchOver) {
        const gamesWon = gameState.games_won || {};
        const p1Games = gamesWon[humanName] || 0;
        const p2Games = gamesWon[opponentName] || 0;
        details += `\n\n🏆 ${gameState.match_winner} wins the match!\nFinal: ${humanName} ${p1Games} - ${p2Games} ${opponentName}`;
    } else if (isGameOver && isMatchMode) {
        const gamesWon = gameState.games_won || {};
        const p1Games = gamesWon[humanName] || 0;
        const p2Games = gamesWon[opponentName] || 0;
        details += `\n\n🏆 ${gameState.game_winner} wins this game!\nMatch: ${humanName} ${p1Games} - ${p2Games} ${opponentName}\nFirst to 2 wins the match.`;
    } else if (isGameOver) {
        details += `\n\n🏆 ${gameState.game_winner} wins the game!`;
    }

    // Update button text based on scenario
    if (isGameOver && isMatchMode && !isMatchOver) {
        elements.nextRoundBtn.textContent = 'Next Game';
    } else if (isGameOver || isMatchOver) {
        elements.nextRoundBtn.textContent = 'See Results';
    } else {
        elements.nextRoundBtn.textContent = 'Next Round';
    }

    elements.roundResultDetails.textContent = details;

    // Update modal labels with actual player names
    elements.modalPlayerLabel.textContent = `${humanName}'s Hand`;
    elements.modalOpponentLabel.textContent = `${opponentName}'s Hand`;

    // Render hands in modal with melds grouped (pass layoff deadwood for defender's hand)
    renderModalHand(elements.modalPlayerHand, result.player_hand,
        defenderIsHuman ? defenderDeadwoodAfter : undefined);
    renderModalHand(elements.modalOpponentHand, result.opponent_hand,
        !defenderIsHuman ? defenderDeadwoodAfter : undefined);

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

    // Resume modal buttons
    elements.resumeYesBtn.addEventListener('click', async () => {
        const gameId = parseInt(elements.resumeYesBtn.dataset.gameId, 10);
        elements.resumeModal.classList.add('hidden');
        try {
            const response = await fetch('/api/game/resume', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId }),
            });
            const state = await response.json();
            if (state && !state.error) {
                renderGameState(state);
                if (!state.your_turn) {
                    await doAiTurn();
                }
            }
        } catch (e) {
            console.error('Failed to resume game:', e);
            startNewGameWithSavedSettings();
        }
    });
    elements.resumeNoBtn.addEventListener('click', () => {
        elements.resumeModal.classList.add('hidden');
        showSettingsModal();
    });
    elements.resumeModal.addEventListener('click', (e) => {
        if (e.target === elements.resumeModal) {
            elements.resumeModal.classList.add('hidden');
            showSettingsModal();
        }
    });

    // Settings modal cancel button and backdrop click
    elements.cancelSettingsBtn.addEventListener('click', () => {
        elements.settingsModal.classList.add('hidden');
    });
    elements.settingsModal.addEventListener('click', (e) => {
        if (e.target === elements.settingsModal) {
            elements.settingsModal.classList.add('hidden');
        }
    });

    // Game mode change handler - show/hide target score
    elements.gameModeSelect.addEventListener('change', () => {
        if (elements.gameModeSelect.value === 'target') {
            elements.targetScoreField.style.display = 'flex';
        } else {
            elements.targetScoreField.style.display = 'none';
        }
    });

    // Oklahoma Gin toggle handler - show/hide spade doubling
    elements.oklahomaGinCheckbox.addEventListener('change', (e) => {
        elements.spadeDoublingField.style.display = e.target.checked ? 'flex' : 'none';
    });

    // Settings form submission
    elements.settingsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        let playerName = elements.playerNameInput.value.trim() || savedSettings.playerName || generatePlayerName();

        // Prevent using "Computer" as player name
        if (playerName.toLowerCase() === 'computer') {
            alert('You cannot use "Computer" as your name - that\'s reserved for the AI!');
            return;
        }

        const aiDifficulty = elements.aiDifficultySelect.value;
        const gameMode = elements.gameModeSelect.value;
        const targetScore = gameMode === 'target' ? parseInt(elements.targetScoreSelect.value) : null;
        const oklahomaGin = elements.oklahomaGinCheckbox.checked;
        const spadeDoubling = elements.spadeDoublingCheckbox.checked;
        const matchMode = elements.matchModeCheckbox.checked;

        // Save to localStorage (always save - either user-provided or generated)
        localStorage.setItem('playerName', playerName);
        localStorage.setItem('aiDifficulty', aiDifficulty);
        localStorage.setItem('gameMode', gameMode);
        if (targetScore) {
            localStorage.setItem('targetScore', targetScore.toString());
        }
        localStorage.setItem('oklahomaGin', oklahomaGin);
        localStorage.setItem('spadeDoubling', spadeDoubling);
        localStorage.setItem('matchMode', matchMode);

        // Update savedSettings (playerName is always set now)
        savedSettings.playerName = playerName;
        savedSettings.aiDifficulty = aiDifficulty;

        const settings = {
            player_name: playerName,
            ai_difficulty: aiDifficulty,
            game_mode: gameMode,
            target_score: targetScore,
            oklahoma_gin: oklahomaGin,
            spade_doubling: spadeDoubling,
            match_mode: matchMode,
        };
        newGame(settings);
    });

    // New game button
    elements.newGameBtn.addEventListener('click', showSettingsModal);

    // Next round button
    elements.nextRoundBtn.addEventListener('click', nextRound);

    // Game over modal buttons
    elements.newGameAfterWinBtn.addEventListener('click', async () => {
        elements.gameOverModal.classList.add('hidden');
        // Start new game immediately with saved settings (Play Again)
        const gameMode = localStorage.getItem('gameMode') || 'target';
        const targetScore = localStorage.getItem('targetScore') || '100';
        const oklahomaGin = localStorage.getItem('oklahomaGin') === 'true';
        const spadeDoubling = localStorage.getItem('spadeDoubling') !== 'false';
        const matchMode = localStorage.getItem('matchMode') === 'true';

        const settings = {
            player_name: savedSettings.playerName,
            ai_difficulty: savedSettings.aiDifficulty,
            game_mode: gameMode,
            target_score: gameMode === 'target' ? parseInt(targetScore) : null,
            oklahoma_gin: oklahomaGin,
            spade_doubling: spadeDoubling,
            match_mode: matchMode,
        };
        await newGame(settings);
    });
    elements.viewStatsAfterWinBtn.addEventListener('click', () => {
        elements.gameOverModal.classList.add('hidden');
        showPlayerStats();
    });
    elements.changeSettingsAfterWinBtn.addEventListener('click', () => {
        elements.gameOverModal.classList.add('hidden');
        showSettingsModal();
    });

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
    elements.statsModal.addEventListener('click', (e) => {
        if (e.target === elements.statsModal) {
            elements.statsModal.classList.add('hidden');
        }
    });

    // Player selection - auto-load on change
    elements.statsPlayerSelect.addEventListener('change', loadSelectedPlayerStats);

    // Clear stats
    elements.clearStatsBtn.addEventListener('click', showClearStatsConfirmation);
    elements.clearStatsConfirmBtn.addEventListener('click', confirmClearStats);
    elements.clearStatsCancelBtn.addEventListener('click', () => {
        elements.clearStatsModal.classList.add('hidden');
    });

    // Score History button and modal
    elements.scoreHistoryBtn.addEventListener('click', showScoreHistory);
    elements.scoreHistoryCloseBtn.addEventListener('click', () => {
        elements.scoreHistoryModal.classList.add('hidden');
    });
    elements.scoreHistoryModal.addEventListener('click', (e) => {
        if (e.target === elements.scoreHistoryModal) {
            elements.scoreHistoryModal.classList.add('hidden');
        }
    });

    // Mini Games modal
    elements.miniGamesBtn.addEventListener('click', () => {
        elements.miniGamesModal.classList.remove('hidden');
    });
    elements.miniGamesCloseBtn.addEventListener('click', () => {
        elements.miniGamesModal.classList.add('hidden');
    });
    elements.miniGamesModal.addEventListener('click', (e) => {
        if (e.target === elements.miniGamesModal) {
            elements.miniGamesModal.classList.add('hidden');
        }
    });

    // Initialize sort button active state
    updateSortButtonStates();

    // Load player names for autocomplete (settings modal is visible by default on page load)
    loadPlayerNamesForSettings();

    // Try to restore existing game, or start new one
    restoreOrStartGame();
}

// Try to restore an existing game session, or start a new game
async function restoreOrStartGame() {
    let sessionState = null;

    try {
        // Check if there's an existing game in progress (session cookie)
        const response = await fetch(`${API_BASE}/state`);
        const state = await response.json();

        if (state && !state.error && state.hand && state.hand.length > 0) {
            sessionState = state;
        }
    } catch (e) {
        console.log('Error checking for existing game:', e);
    }

    // Check for resumable games in the database
    const playerName = savedSettings.playerName;
    if (playerName) {
        try {
            const response = await fetch(`/api/games/resumable?player_name=${encodeURIComponent(playerName)}`);
            const data = await response.json();
            if (data.games && data.games.length > 0) {
                const resumableGame = data.games[0]; // Most recent
                const sessionGameId = sessionState ? sessionState.game_id : null;

                // Show modal if the most recent resumable game differs from the session game
                if (resumableGame.game_id !== sessionGameId) {
                    elements.settingsModal.classList.add('hidden');
                    showResumePrompt(data.games);
                    return;
                }
            }
        } catch (e) {
            console.log('Error checking for resumable games:', e);
        }
    }

    // If session has a valid game, restore it
    if (sessionState) {
        console.log('Restoring existing game session');
        elements.settingsModal.classList.add('hidden');
        renderGameState(sessionState);
        return;
    }

    // No existing or resumable game - start a new one
    startNewGameWithSavedSettings();
}

// Show the resume prompt modal with the most recent resumable game
function showResumePrompt(games) {
    const game = games[0]; // Most recent

    // Format relative time
    let timeAgo = '';
    try {
        const date = new Date(game.started_at);
        const now = new Date();
        const diffMs = now - date;
        const diffHr = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffHr / 24);
        if (diffHr < 1) timeAgo = 'just now';
        else if (diffHr < 24) timeAgo = `${diffHr} hour${diffHr > 1 ? 's' : ''} ago`;
        else timeAgo = `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    } catch (e) { /* ignore */ }

    const scoreInfo = game.target_score
        ? `${game.p1_score} / ${game.target_score} - ${game.p2_score} / ${game.target_score}`
        : `${game.p1_score} - ${game.p2_score}`;

    const settings = [];
    if (game.ai_difficulty) settings.push(game.ai_difficulty.charAt(0).toUpperCase() + game.ai_difficulty.slice(1) + ' AI');
    if (game.oklahoma_gin) settings.push('Oklahoma Gin');
    if (game.match_mode) settings.push('Match Play');

    elements.resumeGameDetails.innerHTML = `
        <div><span class="resume-detail-label">Players:</span> <span class="resume-detail-value">${game.player1_name} vs ${game.player2_name}</span></div>
        <div><span class="resume-detail-label">Score:</span> <span class="resume-detail-value">${scoreInfo}</span></div>
        <div><span class="resume-detail-label">Hands played:</span> <span class="resume-detail-value">${game.hand_count}</span></div>
        ${timeAgo ? `<div><span class="resume-detail-label">Started:</span> <span class="resume-detail-value">${timeAgo}</span></div>` : ''}
        ${settings.length > 0 ? `<div><span class="resume-detail-label">Settings:</span> <span class="resume-detail-value">${settings.join(', ')}</span></div>` : ''}
    `;

    // Store game ID for the resume button handler
    elements.resumeYesBtn.dataset.gameId = game.game_id;

    elements.resumeModal.classList.remove('hidden');
}

// Start a new game using saved localStorage settings
function startNewGameWithSavedSettings() {
    console.log('Starting new game with saved settings');

    // Generate player name if none saved
    if (!savedSettings.playerName) {
        savedSettings.playerName = generatePlayerName();
        localStorage.setItem('playerName', savedSettings.playerName);
    }

    const gameMode = localStorage.getItem('gameMode') || 'target';
    const targetScore = localStorage.getItem('targetScore') || '100';
    const oklahomaGin = localStorage.getItem('oklahomaGin') === 'true';
    const spadeDoubling = localStorage.getItem('spadeDoubling') !== 'false';
    const matchMode = localStorage.getItem('matchMode') === 'true';

    const settings = {
        player_name: savedSettings.playerName,
        ai_difficulty: savedSettings.aiDifficulty,
        game_mode: gameMode,
        target_score: gameMode === 'target' ? parseInt(targetScore) : null,
        oklahoma_gin: oklahomaGin,
        spade_doubling: spadeDoubling,
        match_mode: matchMode,
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

// Track currently viewed player stats
let currentViewedPlayer = null;

// Fetch and display player stats
async function showPlayerStats() {
    // Get player name from current game state if available, otherwise use saved settings
    let playerName = savedSettings.playerName || 'Player';
    if (gameState && gameState.scores) {
        const playerNames = Object.keys(gameState.scores);
        if (playerNames.length > 0 && playerNames[0] !== 'Computer') {
            playerName = playerNames[0];
        }
    }

    elements.statsModal.classList.remove('hidden');

    // Load player list
    await loadPlayerList();

    // Set current player in selector
    elements.statsPlayerSelect.value = playerName;
    currentViewedPlayer = playerName;

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
            `<option value="${p.name}">${p.name} (${p.total_hands} hands, ${(p.win_rate * 100).toFixed(0)}% wins)</option>`
        ).join('');

        // If current player not in list, add them
        let currentPlayerName = savedSettings.playerName || 'Player';
        if (gameState && gameState.scores) {
            const playerNames = Object.keys(gameState.scores);
            if (playerNames.length > 0 && playerNames[0] !== 'Computer') {
                currentPlayerName = playerNames[0];
            }
        }
        const playerExists = players.some(p => p.name === currentPlayerName);
        if (!playerExists) {
            elements.statsPlayerSelect.innerHTML =
                `<option value="${currentPlayerName}">${currentPlayerName} (0 hands)</option>` +
                elements.statsPlayerSelect.innerHTML;
        }
    } catch (error) {
        console.error('Failed to load player list:', error);
        elements.statsPlayerSelect.innerHTML = '<option value="">Error loading players</option>';
    }
}

async function loadSelectedPlayerStats() {
    const playerName = elements.statsPlayerSelect.value.trim();
    if (!playerName) return;

    currentViewedPlayer = playerName;
    await loadStatsForPlayer(playerName);

    // Enable/disable clear button based on whether viewing current player
    // Get current player name from game state if available
    let currentPlayerName = savedSettings.playerName || 'Player';
    if (gameState && gameState.scores) {
        const playerNames = Object.keys(gameState.scores);
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
                    <p>No statistics available yet for <strong>${playerName}</strong>.</p>
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

function showClearStatsConfirmation() {
    const playerName = currentViewedPlayer;
    if (!playerName) return;

    elements.clearStatsPlayerName.textContent = playerName;
    elements.clearStatsModal.classList.remove('hidden');
}

async function confirmClearStats() {
    const playerName = currentViewedPlayer;
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

function showGameOver(winner, scores, targetScore, matchMode, gamesWon, matchWinner) {
    // Hide round modal if it's showing
    elements.roundModal.classList.add('hidden');

    // Determine winner's score
    const winnerScore = scores[winner] || 0;
    const loserName = Object.keys(scores).find(name => name !== winner);
    const loserScore = scores[loserName] || 0;

    // Build game over details based on match mode
    if (matchMode && gamesWon) {
        const playerDisplayName = gameState.player_name || savedSettings.playerName || 'Player';
        if (matchWinner) {
            // Match is complete
            elements.gameOverTitle.textContent = `🎉 Match Complete!`;
            const playerGames = gamesWon[gameState.player_name] || 0;
            const aiGames = gamesWon['Computer'] || 0;
            elements.gameOverDetails.innerHTML = `
                <div style="text-align: center; padding: 20px;">
                    <p style="font-size: 1.5em; margin-bottom: 20px;">
                        <strong>${matchWinner}</strong> wins the match!
                    </p>
                    <div style="font-size: 1.2em; margin: 20px 0;">
                        <div style="margin: 10px 0;">
                            Match Score: ${playerDisplayName} ${playerGames} - ${aiGames} Computer
                        </div>
                    </div>
                </div>
            `;
        } else {
            // Game over but match continues
            const playerGames = gamesWon[gameState.player_name] || 0;
            const aiGames = gamesWon['Computer'] || 0;
            elements.gameOverTitle.textContent = `Game Complete!`;
            elements.gameOverDetails.innerHTML = `
                <div style="text-align: center; padding: 20px;">
                    <p style="font-size: 1.5em; margin-bottom: 20px;">
                        <strong>${winner}</strong> wins this game!
                    </p>
                    <div style="font-size: 1.2em; margin: 20px 0;">
                        <div style="margin: 10px 0;">
                            Match Score: ${playerDisplayName} ${playerGames} - ${aiGames} Computer
                        </div>
                        <div style="margin: 10px 0;">
                            First to win 2 games wins the match!
                        </div>
                    </div>
                </div>
            `;
            elements.newGameAfterWinBtn.textContent = 'Next Game';
        }
    } else {
        // Standard mode
        elements.gameOverTitle.textContent = `🎉 ${winner} Wins!`;
        elements.gameOverDetails.innerHTML = `
            <div style="text-align: center; padding: 20px;">
                <p style="font-size: 1.5em; margin-bottom: 20px;">
                    <strong>${winner}</strong> reached ${targetScore} points!
                </p>
                <div style="font-size: 1.2em; margin: 20px 0;">
                    <div style="margin: 10px 0;">
                        <strong>${winner}:</strong> ${winnerScore} points
                    </div>
                    <div style="margin: 10px 0;">
                        <strong>${loserName}:</strong> ${loserScore} points
                    </div>
                </div>
            </div>
        `;
        elements.newGameAfterWinBtn.textContent = 'New Game';
    }

    // Show game over modal
    elements.gameOverModal.classList.remove('hidden');
}

// Store player names for replay
let scoreHistoryPlayerNames = { player1: '', player2: '' };

async function showScoreHistory() {
    elements.scoreHistoryModal.classList.remove('hidden');
    elements.scoreHistoryContent.innerHTML = '<div class="score-loading">Loading history...</div>';

    try {
        const response = await fetch('/api/game/score-history');
        if (!response.ok) throw new Error('Failed to load history');

        const history = await response.json();

        // Store player names for replay
        scoreHistoryPlayerNames.player1 = history.player1_name;
        scoreHistoryPlayerNames.player2 = history.player2_name;

        if (!history.rounds || history.rounds.length === 0) {
            elements.scoreHistoryContent.innerHTML = `
                <div class="score-empty" style="text-align: center; padding: 20px; color: rgba(255,255,255,0.6);">
                    No rounds played yet in this game.
                </div>
            `;
            return;
        }

        // Render table
        let html = `
            <table class="score-history-table">
                <thead>
                    <tr>
                        <th>Round</th>
                        <th>Winner</th>
                        <th>Points</th>
                        <th>${history.player1_name}</th>
                        <th>${history.player2_name}</th>
                    </tr>
                </thead>
                <tbody>
        `;

        history.rounds.forEach(round => {
            const badges = [];
            if (round.is_gin) badges.push('<span class="score-badge score-badge-gin">GIN</span>');
            if (round.is_undercut) badges.push('<span class="score-badge score-badge-undercut">UNDERCUT</span>');
            if (round.is_draw) badges.push('<span class="score-badge score-badge-draw">DRAW</span>');

            html += `
                <tr class="score-history-row clickable" data-hand-id="${round.hand_id}" title="Click to view turn-by-turn replay">
                    <td>${round.hand_number}</td>
                    <td>${round.winner || 'Draw'}${badges.join('')}</td>
                    <td>${round.points}</td>
                    <td>${round.cumulative_p1}</td>
                    <td>${round.cumulative_p2}</td>
                </tr>
            `;
        });

        html += `
                </tbody>
            </table>
        `;

        elements.scoreHistoryContent.innerHTML = html;

        // Add click handlers for replay
        elements.scoreHistoryContent.querySelectorAll('.score-history-row.clickable').forEach(row => {
            row.addEventListener('click', () => {
                const handId = parseInt(row.dataset.handId, 10);
                openHandReplay(handId);
            });
        });

    } catch (error) {
        console.error('Failed to load score history:', error);
        elements.scoreHistoryContent.innerHTML = `
            <div class="score-error" style="text-align: center; padding: 20px; color: #f44336;">
                Failed to load score history. Please try again.
            </div>
        `;
    }
}

// Hand replay instance
let handReplay = null;

function openHandReplay(handId) {
    // Hide score history modal
    elements.scoreHistoryModal.classList.add('hidden');

    // Show replay modal
    elements.replayModal.classList.remove('hidden');

    // Create or reuse replay instance
    if (!handReplay) {
        handReplay = new HandReplay('replay-container', {
            showControls: true,
            showTurnList: true,
            onClose: closeHandReplay
        });
    }

    // Load the hand
    handReplay.loadHand(handId, scoreHistoryPlayerNames.player1, scoreHistoryPlayerNames.player2);
}

function closeHandReplay() {
    elements.replayModal.classList.add('hidden');
    // Show score history modal again
    elements.scoreHistoryModal.classList.remove('hidden');
}

// Start the game when page loads
document.addEventListener('DOMContentLoaded', init);
