// Assist mode: helpful cards and the card tracker.
import { elements } from './dom.js';

// Render helpful cards ranking
export function renderHelpfulCards(helpfulness) {
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
export function renderCardTracker(state) {
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
