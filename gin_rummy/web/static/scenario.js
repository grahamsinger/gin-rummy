/**
 * Scenario Quiz page: play a frozen mid-game position, compare your
 * choices against the AI panel.
 */

import {
    RED_SUIT_LETTERS as RED_SUITS,
    SUIT_SYMBOLS_BY_LETTER as SUIT_SYMBOLS,
    sortCards,
} from './card-utils.js';

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
        .querySelectorAll('.decision-buttons button, .table-piles button, #newScenarioBtn')
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
    if (!cardIds || cardIds.length === 0) return '<span class="none">none</span>';
    return cardIds.map((c) => cardChip(c, extraClasses)).join('');
}

// Every card the opponent took from the pile, in pickup order; the ones
// they have since thrown back are marked
function pickupChips() {
    const returned = new Set(state.opponent_returned || []);
    const pickups = [...new Set(state.opponent_pickups || [])];
    if (pickups.length === 0) return '<span class="none">none</span>';
    return pickups.map((c) => cardChip(c, returned.has(c) ? 'small returned' : 'small')).join('');
}

function pickupNote() {
    if (!state.opponent_returned || state.opponent_returned.length === 0) return '';
    return '<span class="position-note">crossed out = thrown back since</span>';
}

function renderHand() {
    const container = el('handDisplay');
    const selectable = state.phase === 'discard';
    const drawnId = state.drawn_card ? state.drawn_card.id : null;
    const blockedId = state.blocked_card;

    // Once discarded, the card is on the pile, not in the hand. A meld that
    // held it survives only if three cards remain and, for a run, the card
    // came off an end; otherwise the rest shows as loose cards.
    const discarded = state.user_discard;
    const melds = (state.melds || [])
        .map((meld) => {
            const at = meld.cards.indexOf(discarded);
            if (at === -1) return meld;
            const offEnd = at === 0 || at === meld.cards.length - 1;
            if (meld.cards.length < 4 || (meld.type === 'run' && !offEnd)) return null;
            return { ...meld, cards: meld.cards.filter((c) => c !== discarded) };
        })
        .filter(Boolean);

    const inMeld = new Set();
    melds.forEach((meld) => {
        meld.cards.forEach((c) => inMeld.add(c));
    });

    // Melds render in the server's meld order (runs sorted low-to-high);
    // remaining hand cards are deadwood, sorted the way the main game sorts them
    const sortMode = localStorage.getItem('sortMode') || 'value';
    const deadwood = sortCards(
        state.hand.filter((c) => !inMeld.has(c.id) && c.id !== discarded),
        sortMode
    ).map((c) => c.id);

    const renderCard = (cardId) => {
        let classes = '';
        if (cardId === drawnId) classes += ' drawn';
        if (selectable) {
            classes += cardId === blockedId ? ' blocked' : ' selectable';
        }
        return cardChip(cardId, classes.trim());
    };

    let html = '';
    melds.forEach((meld) => {
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

function analysisPending() {
    return !!(state && state.pending && state.pending.length);
}

// The analysis runs in the background on the server. Once the scenario is
// complete, check back until it has finished.
let pollTimer = null;

function pollForAnalysis() {
    clearTimeout(pollTimer);
    if (!state || state.phase !== 'done' || !analysisPending()) return;
    const seed = state.seed;
    pollTimer = setTimeout(async () => {
        if (!busy) {
            const latest = await api('/state');
            // Ignore the answer if the player has moved on to another scenario meanwhile
            if (latest && !busy && state.seed === seed && latest.seed === seed) {
                const landed = !(latest.pending && latest.pending.length);
                state = latest;
                render();
                if (landed) announceVerdict();
                return;
            }
        }
        pollForAnalysis();
    }, 500);
}

// The moment the analysis arrives: flash the panels it filled in and bring
// the verdict into view
function announceVerdict() {
    for (const id of ['revealPanel', 'scoreboardPanel', 'decisionPanel']) {
        const panel = el(id);
        panel.classList.remove('just-landed');
        void panel.offsetWidth; // restart the animation
        panel.classList.add('just-landed');
    }
    el('revealPanel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// "Draw 3/3 agreed · Discard 2/3 agreed" for the scenario just judged
function verdictSummary() {
    const labels = { draw: 'Draw', discard: 'Discard', knock: 'Knock' };
    return Object.keys(labels)
        .filter((k) => state.reveals && state.reveals[k] && state.reveals[k].length)
        .map((k) => {
            const rows = state.reveals[k];
            const agreed = rows.filter((r) => r.agrees).length;
            const cls = agreed === rows.length ? 'all' : agreed === 0 ? 'nobody' : 'some';
            return `<span class="verdict ${cls}">${labels[k]}: ${agreed}/${rows.length} AIs agreed</span>`;
        })
        .join('');
}

function render() {
    if (!state) return;
    pollForAnalysis();

    el('scenarioNum').textContent = state.seed != null ? `Seed ${state.seed}` : '';

    if (state.phase === 'idle' || !state.hand) {
        el('positionStats').innerHTML = '';
        el('positionInfo').innerHTML = '';
        el('tablePiles').innerHTML = '';
        el('handDisplay').innerHTML = '';
        el('decisionTitle').textContent = 'Ready';
        el('decisionPrompt').textContent = 'Click "New Scenario" to get a position.';
        el('decisionButtons').innerHTML = '';
        renderScoreboard();
        return;
    }

    const stat = (label, value) =>
        `<div class="stat"><span class="stat-value">${value}</span><span class="stat-label">${label}</span></div>`;
    // How far through the hand this is: the deck only shrinks, and the hand
    // ends with no winner once it is down to the last few cards
    const drawable = Math.max(state.deck_remaining - state.deck_min, 0);
    const span = state.deck_start - state.deck_min;
    const left = Math.round((100 * drawable) / span);
    const deckStat = `
        <div class="stat deck-stat">
            <span class="stat-value">${state.deck_remaining} <span class="stat-of">of ${state.deck_start}</span></span>
            <div class="deck-bar" role="img" aria-label="${state.deck_remaining} of ${state.deck_start} cards left in the deck">
                <div class="deck-bar-fill" style="width:${left}%"></div>
            </div>
            <span class="stat-label">Cards left in deck · nobody wins the hand if it gets down to ${state.deck_min}</span>
        </div>`;

    el('positionStats').innerHTML =
        stat(`Your turn · ${state.turns_played} played so far`, `#${state.your_turn}`) +
        stat('Your deadwood', state.post_discard_deadwood ?? state.deadwood) +
        stat('Knock at', `≤${state.knock_threshold}`) +
        deckStat;

    const row = (label, content, note = '') =>
        `<div class="position-label">${label}</div><div class="position-cards">${content}${note}</div>`;
    // The deck and the face-up card are drawn as piles in the decision panel
    el('positionInfo').innerHTML =
        row('Opponent picked up', pickupChips(), pickupNote()) + row('Buried', chipList(state.buried));

    el('handLabel').textContent =
        state.phase === 'discard' ? 'Your hand — click a card to discard' : 'Your hand';
    renderHand();
    renderPiles();
    renderDecision();
    renderReveals();
    renderScoreboard();
}

// The deck (face down) and the discard pile (top card face up), laid out as
// on the table. They are the draw controls during the draw decision.
function renderPiles() {
    const container = el('tablePiles');
    const clickable = state.phase === 'draw';
    const tag = clickable ? 'button' : 'div';
    // Once you have discarded, your card is the top of the pile
    const top = state.user_discard ? { id: state.user_discard } : state.discard_top;

    let face = '<div class="pile-card empty"></div>';
    if (top) {
        const suit = top.id.slice(-1);
        const rank = top.id.slice(0, -1);
        const color = RED_SUITS.has(suit) ? 'red' : 'black';
        const symbol = SUIT_SYMBOLS[suit] || suit;
        face = `
            <div class="pile-card face ${color}">
                <span class="pile-corner">${rank}<br>${symbol}</span>
                <span class="pile-suit">${symbol}</span>
            </div>`;
    }

    container.innerHTML = `
        <${tag} class="pile" id="drawDeckBtn" ${clickable ? 'type="button"' : ''}>
            <div class="pile-card back"></div>
            <span class="pile-label">Deck · ${state.deck_remaining} cards</span>
        </${tag}>
        <${tag} class="pile" id="drawPileBtn" ${clickable ? 'type="button"' : ''}>
            ${face}
            <span class="pile-label">Discard pile</span>
        </${tag}>`;

    if (clickable) {
        el('drawDeckBtn').addEventListener('click', () => answerDraw('deck'));
        if (top) el('drawPileBtn').addEventListener('click', () => answerDraw('discard'));
    }
}

function renderDecision() {
    // Finished: the way forward is a new scenario, so that button stands out
    el('newScenarioBtn').classList.toggle('next', state.phase === 'done');

    const title = el('decisionTitle');
    const prompt = el('decisionPrompt');
    const buttons = el('decisionButtons');
    prompt.textContent = '';
    buttons.innerHTML = '';

    if (state.phase === 'draw') {
        title.textContent = 'Decision 1: Draw';
        prompt.textContent = 'Click the deck to draw a new card, or the face-up card to take it.';
    } else if (state.phase === 'discard') {
        title.textContent = 'Decision 2: Discard';
        prompt.innerHTML = `You drew ${cardChip(state.drawn_card.id, 'small')} — click a card below to discard it.`;
    } else if (state.phase === 'knock') {
        title.textContent = 'Decision 3: Knock?';
        prompt.innerHTML = `Discarding ${cardChip(state.user_discard, 'small')} leaves <b>${state.post_discard_deadwood}</b> deadwood.`;
        buttons.innerHTML = `
            <button class="quiz-btn primary" id="knockYesBtn">Knock</button>
            <button class="quiz-btn" id="knockNoBtn">Keep playing</button>`;
        el('knockYesBtn').addEventListener('click', () => answerKnock(true));
        el('knockNoBtn').addEventListener('click', () => answerKnock(false));
    } else if (state.phase === 'done') {
        if (analysisPending()) {
            title.textContent = 'Scenario complete';
            prompt.innerHTML = '<span class="thinking">The AIs are judging your choices…</span>';
        } else {
            title.textContent = 'Scenario judged';
            prompt.innerHTML = `${verdictSummary()}<div class="verdict-hint">Details are below.</div>`;
        }
        buttons.innerHTML = '<button class="quiz-btn next" id="nextScenarioBtn">Next scenario →</button>';
        el('nextScenarioBtn').addEventListener('click', newScenario);
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

// The AIs' choices are shown only once the scenario is complete, so their
// reasoning about one decision cannot give away the next
function renderReveals() {
    const panel = el('revealPanel');
    const content = el('revealContent');
    const labels = { draw: 'Draw decision', discard: 'Discard decision', knock: 'Knock decision' };

    if (state.phase !== 'done') {
        panel.style.display = 'none';
        content.innerHTML = '';
        return;
    }
    panel.style.display = '';
    if (analysisPending()) {
        content.innerHTML = '<span class="thinking">The AIs are analysing your choices…</span>';
        return;
    }

    const sections = [];
    for (const key of ['draw', 'discard', 'knock']) {
        const rows = state.reveals && state.reveals[key];
        if (!rows) continue;
        const body = rows.length ? rows.map(revealRow).join('') : '<span class="none">Analysis failed.</span>';
        sections.push(`<div class="reveal-section"><h3>${labels[key]}</h3>${body}</div>`);
    }
    content.innerHTML = sections.join('');
}

function renderScoreboard() {
    const table = el('scoreboard');
    const kinds = ['draw', 'discard', 'knock'];

    // Mid-scenario the totals would show whether the AIs agreed with the
    // answers so far, so the board waits for the scenario to finish
    const midScenario =
        state && (state.phase === 'discard' || state.phase === 'knock' || analysisPending());
    const judged = state && state.phase === 'done' && !analysisPending();
    el('judgingChip').textContent = midScenario ? 'waiting for this scenario' : judged ? 'updated' : '';
    el('judgingChip').className = `judging-chip ${midScenario ? 'waiting' : judged ? 'updated' : ''}`;
    if (midScenario && table.innerHTML) return;

    // This scenario's result per AI and decision, shown beside the totals
    const latest = (name, kind) => {
        const rows = judged && state.reveals && state.reveals[kind];
        const row = rows && rows.find((r) => r.name === name);
        if (!row) return '';
        return row.agrees
            ? '<span class="latest agrees" title="Agreed with you this scenario">✓</span>'
            : '<span class="latest disagrees" title="Chose differently this scenario">✗</span>';
    };

    // All-time totals from the database; this session's tallies if it is unavailable
    let perAi = {};
    let note = '';
    if (state && state.lifetime) {
        perAi = state.lifetime.by_ai;
        const n = state.lifetime.scenarios;
        note = `All time: ${n} scenario${n === 1 ? '' : 's'} answered.`;
    } else if (state && state.tallies) {
        const decisions = state.decisions || { draw: 0, discard: 0, knock: 0 };
        for (const [name, t] of Object.entries(state.tallies)) {
            perAi[name] = Object.fromEntries(kinds.map((k) => [k, { agree: t[k], total: decisions[k] }]));
        }
        note = 'This session only (history unavailable).';
    }

    const names = Object.keys(perAi);
    if (!names.length) {
        table.innerHTML = '<tr><td class="none">Answer a scenario to start the tally.</td></tr>';
        el('statusLine').textContent = '';
        return;
    }

    let html = `<tr><th>AI</th><th class="num">Draw</th><th class="num">Discard</th><th class="num">Knock</th><th class="num">Overall</th></tr>`;
    for (const name of names) {
        const t = perAi[name];
        const agree = kinds.reduce((sum, k) => sum + t[k].agree, 0);
        const total = kinds.reduce((sum, k) => sum + t[k].total, 0);
        const pct = total ? Math.round((100 * agree) / total) : 0;
        html += `<tr>
            <td>${name}</td>
            ${kinds.map((k) => `<td class="num">${latest(name, k)}${t[k].agree}/${t[k].total}</td>`).join('')}
            <td class="num">${pct}%</td>
        </tr>`;
    }
    table.innerHTML = html;
    const legend = judged ? ' ✓ / ✗ = this scenario.' : '';
    el('statusLine').textContent = `Agreement = times the AI made the same choice as you.${legend} ${note}`;
}

// ------------------------------------------------------------------
// Actions
// ------------------------------------------------------------------

function answerDraw(source) {
    withBusy('Drawing…', () => api('/draw', { source }));
}

function discardCard(cardId) {
    withBusy('Discarding…', () => api('/discard', { card: cardId }));
}

function answerKnock(knock) {
    withBusy('Answering…', () => api('/knock', { knock }));
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
