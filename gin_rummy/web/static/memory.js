// Card Memory Game

const SUITS = ['spades', 'hearts', 'diamonds', 'clubs'];
const RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
const SUIT_SYMBOLS = window.CardUtils.SUIT_SYMBOLS_BY_NAME;  // shared from card-utils.js

// Progression table
const ROUNDS = [
    { cards: 3, time: 3.0 },
    { cards: 4, time: 3.0 },
    { cards: 5, time: 2.5 },
    { cards: 6, time: 2.5 },
    { cards: 7, time: 2.0 },
];

function getRoundConfig(round) {
    if (round <= ROUNDS.length) return ROUNDS[round - 1];
    const extraCards = round - ROUNDS.length;
    return {
        cards: 7 + extraCards,
        time: Math.max(1.5, 2.0),
    };
}

// Game state
let phase = 'READY'; // READY, REVEALING, SELECTING, RESULTS
let currentRound = 1;
let targetCards = [];  // Cards the player needs to find
let selectedCards = new Set();  // Card IDs the player has selected
let timerInterval = null;
let highScore = parseInt(localStorage.getItem('memoryHighScore') || '0', 10);

// DOM elements
const els = {
    roundDisplay: document.getElementById('round-display'),
    cardsDisplay: document.getElementById('cards-display'),
    timerDisplay: document.getElementById('timer-display'),
    selectedCount: document.getElementById('selected-count'),
    targetCount: document.getElementById('target-count'),
    revealArea: document.getElementById('reveal-area'),
    resultsArea: document.getElementById('results-area'),
    selectionGrid: document.getElementById('selection-grid'),
    startBtn: document.getElementById('start-btn'),
    submitBtn: document.getElementById('submit-btn'),
    nextBtn: document.getElementById('next-btn'),
    restartBtn: document.getElementById('restart-btn'),
    gridLegend: document.getElementById('grid-legend'),
    highScore: document.getElementById('high-score'),
};

// Generate full 52-card deck
function generateDeck() {
    const deck = [];
    for (const suit of SUITS) {
        for (const rank of RANKS) {
            deck.push({
                id: rank + suit[0].toUpperCase(),
                rank,
                suit,
            });
        }
    }
    return deck;
}

// Fisher-Yates shuffle
function shuffle(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
}

// Create a card element (reuses game.js card styling)
function createCardElement(card) {
    const div = document.createElement('div');
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

// Build the 52-card selection grid (4 rows x 13 cols)
function buildGrid() {
    els.selectionGrid.innerHTML = '';

    for (const suit of SUITS) {
        const row = document.createElement('div');
        row.className = 'grid-row';

        // Suit label
        const label = document.createElement('div');
        label.className = 'suit-label';
        if (suit === 'hearts' || suit === 'diamonds') {
            label.classList.add('red-label');
        }
        label.textContent = SUIT_SYMBOLS[suit];
        row.appendChild(label);

        for (const rank of RANKS) {
            const cardId = rank + suit[0].toUpperCase();
            const cell = document.createElement('div');
            cell.className = 'grid-card';
            cell.dataset.cardId = cardId;
            cell.textContent = rank + SUIT_SYMBOLS[suit];

            if (suit === 'hearts' || suit === 'diamonds') {
                cell.classList.add('red-card');
            }

            cell.addEventListener('click', () => handleGridClick(cardId));
            row.appendChild(cell);
        }

        els.selectionGrid.appendChild(row);
    }
}

// Handle clicking a card in the grid
function handleGridClick(cardId) {
    if (phase !== 'SELECTING') return;

    const config = getRoundConfig(currentRound);
    const cell = els.selectionGrid.querySelector(`[data-card-id="${cardId}"]`);
    if (!cell) return;

    if (selectedCards.has(cardId)) {
        // Deselect
        selectedCards.delete(cardId);
        cell.classList.remove('selected');
    } else {
        // Select (only if under target count)
        if (selectedCards.size >= config.cards) return;
        selectedCards.add(cardId);
        cell.classList.add('selected');
    }

    updateSelectedCount();
}

function updateSelectedCount() {
    els.selectedCount.textContent = selectedCards.size;
    const config = getRoundConfig(currentRound);
    els.submitBtn.disabled = selectedCards.size !== config.cards;
}

// Update the status bar
function updateStatus() {
    const config = getRoundConfig(currentRound);
    els.roundDisplay.textContent = currentRound;
    els.cardsDisplay.textContent = config.cards;
    els.timerDisplay.textContent = config.time.toFixed(1) + 's';
    els.targetCount.textContent = config.cards;
    els.selectedCount.textContent = selectedCards.size;
}

// Show/hide buttons
function showButtons(...names) {
    els.startBtn.style.display = 'none';
    els.submitBtn.style.display = 'none';
    els.nextBtn.style.display = 'none';
    els.restartBtn.style.display = 'none';
    for (const name of names) {
        els[name + 'Btn'].style.display = '';
    }
}

function updateHighScoreDisplay() {
    if (highScore > 0) {
        els.highScore.innerHTML = `Best: Round <strong>${highScore}</strong>`;
    } else {
        els.highScore.textContent = '';
    }
}

// ---- Phase transitions ----

function startRound() {
    phase = 'REVEALING';
    const config = getRoundConfig(currentRound);
    selectedCards.clear();
    els.resultsArea.innerHTML = '';
    updateStatus();
    showButtons();
    clearGridStates();

    // Pick random cards
    const deck = generateDeck();
    const shuffled = shuffle(deck);
    targetCards = shuffled.slice(0, config.cards);

    // Show cards face-up in reveal area
    els.revealArea.innerHTML = '';
    const revealRow = document.createElement('div');
    revealRow.className = 'reveal-cards';
    for (const card of targetCards) {
        revealRow.appendChild(createCardElement(card));
    }
    els.revealArea.appendChild(revealRow);

    // Start countdown
    let remaining = config.time;
    els.timerDisplay.textContent = remaining.toFixed(1) + 's';

    timerInterval = setInterval(() => {
        remaining -= 0.1;
        if (remaining <= 0) {
            remaining = 0;
            clearInterval(timerInterval);
            timerInterval = null;
            enterSelecting();
        }
        els.timerDisplay.textContent = remaining.toFixed(1) + 's';
    }, 100);

    // Disable grid during reveal
    setGridDisabled(true);

    // Hide legend during reveal
    els.gridLegend.style.display = 'none';
}

function enterSelecting() {
    phase = 'SELECTING';

    // Hide revealed cards
    els.revealArea.innerHTML = '<span class="reveal-message">Select the cards you saw</span>';

    // Enable grid
    setGridDisabled(false);

    // Show submit button
    showButtons('submit');
    els.submitBtn.disabled = true;
    updateSelectedCount();

    // Show selection legend
    els.gridLegend.style.display = '';
    els.gridLegend.innerHTML = '<div class="legend-item"><div class="legend-swatch selected-swatch"></div> Selected</div>';
}

function submitAnswer() {
    if (phase !== 'SELECTING') return;
    phase = 'RESULTS';

    const targetIds = new Set(targetCards.map(c => c.id));
    let correctCount = 0;
    let missedCount = 0;
    let wrongCount = 0;

    // Classify each grid card
    const allCells = els.selectionGrid.querySelectorAll('.grid-card');
    allCells.forEach(cell => {
        const cardId = cell.dataset.cardId;
        const wasTarget = targetIds.has(cardId);
        const wasSelected = selectedCards.has(cardId);

        cell.classList.remove('selected');

        if (wasTarget && wasSelected) {
            cell.classList.add('correct');
            correctCount++;
        } else if (wasTarget && !wasSelected) {
            cell.classList.add('missed');
            missedCount++;
        } else if (!wasTarget && wasSelected) {
            cell.classList.add('wrong');
            wrongCount++;
        }
    });

    setGridDisabled(true);

    const success = correctCount === targetIds.size && wrongCount === 0;

    // Show results
    const config = getRoundConfig(currentRound);
    const summaryDiv = document.createElement('div');
    summaryDiv.className = `results-summary ${success ? 'success' : 'failure'}`;

    if (success) {
        summaryDiv.innerHTML = `
            <div class="result-title">Perfect!</div>
            <div>You found all ${config.cards} cards correctly.</div>
        `;
        showButtons('next');
    } else {
        // Update high score
        const finalRound = currentRound - 1;
        if (finalRound > highScore) {
            highScore = finalRound;
            localStorage.setItem('memoryHighScore', highScore.toString());
        }

        let details = [];
        if (correctCount > 0) details.push(`${correctCount} correct`);
        if (missedCount > 0) details.push(`${missedCount} missed`);
        if (wrongCount > 0) details.push(`${wrongCount} wrong`);

        summaryDiv.innerHTML = `
            <div class="result-title">Game Over</div>
            <div>${details.join(', ')}</div>
            <div style="margin-top:0.5rem; color: rgba(255,255,255,0.6);">
                You reached Round ${currentRound}${highScore > 0 ? ` (Best: Round ${highScore})` : ''}
            </div>
        `;
        showButtons('restart');
    }

    els.resultsArea.innerHTML = '';
    els.resultsArea.appendChild(summaryDiv);

    // Update legend to show result colors
    els.gridLegend.style.display = '';
    els.gridLegend.innerHTML = `
        <div class="legend-item"><div class="legend-swatch correct"></div> Correct</div>
        <div class="legend-item"><div class="legend-swatch missed"></div> Missed</div>
        <div class="legend-item"><div class="legend-swatch wrong"></div> Wrong</div>
    `;

    // Re-show target cards and guess in reveal area
    els.revealArea.innerHTML = '';

    // Actual row
    const actualLabel = document.createElement('div');
    actualLabel.className = 'reveal-row-label';
    actualLabel.textContent = 'Actual';
    els.revealArea.appendChild(actualLabel);

    const actualRow = document.createElement('div');
    actualRow.className = 'reveal-cards';
    for (const card of targetCards) {
        actualRow.appendChild(createCardElement(card));
    }
    els.revealArea.appendChild(actualRow);

    // Guess row
    const guessLabel = document.createElement('div');
    guessLabel.className = 'reveal-row-label';
    guessLabel.textContent = 'Your Guess';
    els.revealArea.appendChild(guessLabel);

    const guessRow = document.createElement('div');
    guessRow.className = 'reveal-cards';
    const deck = generateDeck();
    const deckMap = {};
    for (const c of deck) deckMap[c.id] = c;

    // Align guess cards to match actual card positions
    // Correct guesses go in the matching slot; wrong guesses fill missed slots
    const wrongGuesses = [...selectedCards].filter(id => !targetIds.has(id));
    let wrongIdx = 0;
    for (const card of targetCards) {
        if (selectedCards.has(card.id)) {
            // Correct guess — show in matching position
            const el = createCardElement(card);
            el.classList.add('guess-correct');
            guessRow.appendChild(el);
        } else if (wrongIdx < wrongGuesses.length) {
            // Missed card — fill with the next wrong guess to show what was picked instead
            const wrongCard = deckMap[wrongGuesses[wrongIdx]];
            wrongIdx++;
            const el = createCardElement(wrongCard);
            el.classList.add('guess-wrong');
            guessRow.appendChild(el);
        } else {
            // Missed with no more wrong guesses to show (shouldn't happen since counts match)
            const empty = document.createElement('div');
            empty.className = 'card empty';
            guessRow.appendChild(empty);
        }
    }
    els.revealArea.appendChild(guessRow);

    updateHighScoreDisplay();
}

function nextRound() {
    currentRound++;
    startRound();
}

function restart() {
    currentRound = 1;
    phase = 'READY';
    targetCards = [];
    selectedCards.clear();
    els.resultsArea.innerHTML = '';
    els.revealArea.innerHTML = '<span class="reveal-message">Press Start to begin</span>';
    els.gridLegend.style.display = 'none';
    updateStatus();
    showButtons('start');
    clearGridStates();
    setGridDisabled(true);
    updateHighScoreDisplay();
}

// Grid helpers
function setGridDisabled(disabled) {
    const cells = els.selectionGrid.querySelectorAll('.grid-card');
    cells.forEach(cell => {
        if (disabled) {
            cell.classList.add('disabled');
        } else {
            cell.classList.remove('disabled');
        }
    });
}

function clearGridStates() {
    const cells = els.selectionGrid.querySelectorAll('.grid-card');
    cells.forEach(cell => {
        cell.classList.remove('selected', 'correct', 'missed', 'wrong');
    });
}

// Event listeners
els.startBtn.addEventListener('click', startRound);
els.submitBtn.addEventListener('click', submitAnswer);
els.nextBtn.addEventListener('click', nextRound);
els.restartBtn.addEventListener('click', restart);

// Initialize
buildGrid();
setGridDisabled(true);
updateStatus();
updateHighScoreDisplay();
