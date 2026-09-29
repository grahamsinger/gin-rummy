// Showing the AI's turn: its action, last move and Monte Carlo thinking.
import { renderGameState } from './board.js';
import { formatCardId } from './cards.js';
import { elements } from './dom.js';

export async function displayAiAction(action, state) {
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

// Update the persistent last AI move display
export function updateLastAiMove(action) {
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
export function renderMcThinking(mcThinking) {
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
