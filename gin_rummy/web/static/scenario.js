/**
 * Scenario Quiz page: play a frozen mid-game position, compare your
 * choices against the AI panel.
 */

import { RED_SUIT_LETTERS as RED_SUITS, SUIT_SYMBOLS_BY_LETTER as SUIT_SYMBOLS } from './card-utils.js';

const API = '/api/scenario';

let state = null;
let busy = false;

const el = (id) => document.getElementById(id);

// ------------------------------------------------------------------
// API
// ------------------------------------------------------------------

async function api(path, body) {
    const options = body
        ? {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
          }
        : {};
    const response = await fetch(`${API}${path}`, options);
    const data = await response.json();
    if (!response.ok) {
        el('decisionPrompt').textContent = data.detail || data.error || 'An error occurred';
        return null;
    }
    return data;
}

async function withBusy(label, fn) {
    if (busy) return;
    busy = true;
    const title = el('decisionTitle');
    const prev = title.textContent;
    title.innerHTML = `<span class="thinking">${label}</span>`;
    setButtonsEnabled(false);
    try {
        const result = await fn();
        if (result) {
            state = result;
            render();
        } else {
            title.textContent = prev;
        }
    } finally {
        busy = false;
        setButtonsEnabled(true);
    }
}

function setButtonsEnabled(enabled) {
    document
        .querySelectorAll('.decision-buttons button, #newScenarioBtn')
        .forEach((b) => (b.disabled = !enabled));
}

// ------------------------------------------------------------------
// Card rendering
// ------------------------------------------------------------------

function cardChip(cardId, extraClasses = '') {
    const suit = cardId.slice(-1);
    const rank = cardId.slice(0, -1);
    const color = RED_SUITS.has(suit) ? 'red' : 'black';
    return `<span class="quiz-card ${color} ${extraClasses}" data-card="${cardId}">${rank}${SUIT_SYMBOLS[suit] || suit}</span>`;
}

function chipList(cardIds, extraClasses = 'small') {
    if (!cardIds || cardIds.length === 0) return '<span style="color:#666">none</span>';
    return cardIds.map((c) => cardChip(c, extraClasses)).join('');
}

function renderHand() {
    const container = el('handDisplay');
    const selectable = state.phase === 'discard';
    const drawnId = state.drawn_card ? state.drawn_card.id : null;
    const blockedId = state.blocked_card;

    const inMeld = new Set();
    (state.melds || []).forEach((meld) => {
        meld.cards.forEach((c) => inMeld.add(c));
    });

    // Melds render in the server's meld order (runs sorted low-to-high);
    // remaining hand cards are deadwood
    const deadwood = state.hand.map((c) => c.id).filter((id) => !inMeld.has(id));

    const renderCard = (cardId) => {
        let classes = '';
        if (cardId === drawnId) classes += ' drawn';
        if (selectable) {
            classes += cardId === blockedId ? ' blocked' : ' selectable';
        }
        return cardChip(cardId, classes.trim());
    };

    let html = '';
    (state.melds || []).forEach((meld) => {
        html += `<span class="quiz-meld ${meld.type}">${meld.cards.map(renderCard).join('')}</span>`;
    });
    html += deadwood.map(renderCard).join('');
    container.innerHTML = html;

    if (selectable) {
        container.querySelectorAll('.quiz-card.selectable').forEach((chip) => {
            chip.addEventListener('click', () => discardCard(chip.dataset.card));
        });
    }
}

// ------------------------------------------------------------------
// Rendering
// ------------------------------------------------------------------

function render() {
    if (!state) return;

    el('scenarioNum').textContent = state.scenario_num ? `#${state.scenario_num}` : '';

    if (state.phase === 'idle' || !state.hand) {
        el('positionInfo').innerHTML = '';
        el('handDisplay').innerHTML = '';
        el('decisionTitle').textContent = 'Ready';
        el('decisionPrompt').textContent = 'Click "New Scenario" to get a position.';
        el('decisionButtons').innerHTML = '';
        renderScoreboard();
        return;
    }

    // Position info
    const info = [];
    info.push(
        `<span><span class="label">Discard top:</span>${
            state.discard_top ? cardChip(state.discard_top.id, 'small') : '—'
        }</span>`
    );
    info.push(`<span><span class="label">Deck:</span>${state.deck_remaining} cards</span>`);
    info.push(`<span><span class="label">Deadwood:</span>${state.deadwood}</span>`);
    info.push(`<span><span class="label">Knock at:</span>≤${state.knock_threshold}</span>`);
    info.push(
        `<span><span class="label">Opponent picked up:</span>${chipList(state.opponent_pickups)}</span>`
    );
    info.push(`<span><span class="label">Buried:</span>${chipList(state.buried)}</span>`);
    el('positionInfo').innerHTML = info.join('');

    el('handLabel').textContent =
        state.phase === 'discard' ? 'Your hand — click a card to discard' : 'Your hand';
    renderHand();
    renderDecision();
    renderReveals();
    renderScoreboard();
}

function renderDecision() {
    const title = el('decisionTitle');
    const prompt = el('decisionPrompt');
    const buttons = el('decisionButtons');
    prompt.textContent = '';
    buttons.innerHTML = '';

    if (state.phase === 'draw') {
        title.textContent = 'Decision 1: Draw';
        const topCard = state.discard_top ? cardChip(state.discard_top.id, 'small') : '';
        buttons.innerHTML = `
            <button class="quiz-btn primary" id="drawDeckBtn">Draw from deck</button>
            <button class="quiz-btn primary" id="drawPileBtn">Take ${topCard} from pile</button>`;
        el('drawDeckBtn').addEventListener('click', () => answerDraw('deck'));
        el('drawPileBtn').addEventListener('click', () => answerDraw('discard'));
    } else if (state.phase === 'discard') {
        title.textContent = 'Decision 2: Discard';
        prompt.innerHTML = `You drew ${cardChip(state.drawn_card.id, 'small')} — click a card above to discard it.`;
    } else if (state.phase === 'knock') {
        title.textContent = 'Decision 3: Knock?';
        prompt.innerHTML = `Discarding ${cardChip(state.user_discard, 'small')} leaves <b>${state.post_discard_deadwood}</b> deadwood.`;
        buttons.innerHTML = `
            <button class="quiz-btn primary" id="knockYesBtn">Knock</button>
            <button class="quiz-btn" id="knockNoBtn">Keep playing</button>`;
        el('knockYesBtn').addEventListener('click', () => answerKnock(true));
        el('knockNoBtn').addEventListener('click', () => answerKnock(false));
    } else if (state.phase === 'done') {
        title.textContent = 'Scenario complete';
        prompt.textContent = 'Review the AI choices below, then start a new scenario.';
    }
}

function revealRow(row) {
    const marker = row.agrees ? '✓' : '✗';
    const cls = row.agrees ? 'agrees' : 'disagrees';
    let choice = row.choice;
    if (choice === 'deck') choice = 'draw from deck';
    else if (choice === 'discard') choice = 'take from pile';
    let html = `
        <div class="reveal-row ${cls}">
            <span class="reveal-marker">${marker}</span>
            <span class="reveal-name">${row.name}</span>
            <span class="reveal-text">${row.reasoning}</span>
        </div>`;
    if (row.mc_evs && row.mc_evs.length) {
        const evs = row.mc_evs
            .map((e) => `${e.card}: ${e.ev >= 0 ? '+' : ''}${e.ev.toFixed(1)}`)
            .join(' &nbsp; ');
        html += `<div class="mc-evs">MC expected points — ${evs}</div>`;
    }
    return html;
}

function renderReveals() {
    const panel = el('revealPanel');
    const content = el('revealContent');
    const sections = [];
    const labels = { draw: 'Draw decision', discard: 'Discard decision', knock: 'Knock decision' };

    for (const key of ['draw', 'discard', 'knock']) {
        const rows = state.reveals && state.reveals[key];
        if (!rows) continue;
        sections.push(
            `<div class="reveal-section"><h3>${labels[key]}</h3>${rows.map(revealRow).join('')}</div>`
        );
    }

    panel.style.display = sections.length ? '' : 'none';
    content.innerHTML = sections.join('');
}

function renderScoreboard() {
    const table = el('scoreboard');
    const tallies = state && state.tallies ? state.tallies : {};
    const decisions = state && state.decisions ? state.decisions : { draw: 0, discard: 0, knock: 0 };
    const names = Object.keys(tallies);

    if (!names.length) {
        table.innerHTML = '<tr><td style="color:#666">Answer a scenario to start the tally.</td></tr>';
        el('statusLine').textContent = '';
        return;
    }

    let html = `<tr><th>AI</th><th style="text-align:right">Draw</th><th style="text-align:right">Discard</th><th style="text-align:right">Knock</th><th style="text-align:right">Overall</th></tr>`;
    for (const name of names) {
        const t = tallies[name];
        const total = t.draw + t.discard + t.knock;
        const possible = decisions.draw + decisions.discard + decisions.knock;
        const pct = possible ? Math.round((100 * total) / possible) : 0;
        html += `<tr>
            <td>${name}</td>
            <td class="num">${t.draw}/${decisions.draw}</td>
            <td class="num">${t.discard}/${decisions.discard}</td>
            <td class="num">${t.knock}/${decisions.knock}</td>
            <td class="num">${pct}%</td>
        </tr>`;
    }
    table.innerHTML = html;
    el('statusLine').textContent = `Agreement = times the AI made the same choice as you. Seed ${state.seed ?? '—'}.`;
}

// ------------------------------------------------------------------
// Actions
// ------------------------------------------------------------------

function answerDraw(source) {
    withBusy('AIs evaluating the draw…', () => api('/draw', { source }));
}

function discardCard(cardId) {
    withBusy('AIs evaluating the discard…', () => api('/discard', { card: cardId }));
}

function answerKnock(knock) {
    withBusy('AIs evaluating the knock…', () => api('/knock', { knock }));
}

function newScenario() {
    withBusy('Generating scenario…', () => api('/new', {}));
}

el('newScenarioBtn').addEventListener('click', newScenario);

// On load: restore an in-progress scenario or start fresh
(async function init() {
    const current = await api('/state');
    if (current && current.phase && current.phase !== 'idle') {
        state = current;
        render();
    } else {
        newScenario();
    }
})();
