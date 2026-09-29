// The score history modal and the hand replay it opens.
import { escapeHtml as esc } from '../card-utils.js';
import { HandReplay } from '../replay.js';
import { elements } from './dom.js';
import { ui, scoreHistoryPlayerNames } from './state.js';

export async function showScoreHistory() {
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
                        <th>${esc(history.player1_name)}</th>
                        <th>${esc(history.player2_name)}</th>
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
                    <td>${esc(round.winner || 'Draw')}${badges.join('')}</td>
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

function openHandReplay(handId) {
    // Hide score history modal
    elements.scoreHistoryModal.classList.add('hidden');

    // Show replay modal
    elements.replayModal.classList.remove('hidden');

    // Create or reuse replay instance
    if (!ui.handReplay) {
        ui.handReplay = new HandReplay('replay-container', {
            showControls: true,
            showTurnList: true,
            onClose: closeHandReplay
        });
    }

    // Load the hand
    ui.handReplay.loadHand(handId, scoreHistoryPlayerNames.player1, scoreHistoryPlayerNames.player2);
}

function closeHandReplay() {
    elements.replayModal.classList.add('hidden');
    // Show score history modal again
    elements.scoreHistoryModal.classList.remove('hidden');
}
