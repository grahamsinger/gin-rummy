// Round result, game over and resume modals.
import { escapeHtml as esc } from '../card-utils.js';
import { RANK_ORDER, createCardElement, formatCardId } from './cards.js';
import { elements } from './dom.js';
import { ui, savedSettings } from './state.js';

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
export function showRoundResult(result) {
    if (!result) return;

    // Detect game/match end scenarios
    const isGameOver = ui.gameState && ui.gameState.game_over && ui.gameState.game_winner;
    const isMatchMode = ui.gameState && ui.gameState.match_mode;
    const isMatchOver = isMatchMode && ui.gameState.match_winner;

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
    const playerNames = ui.gameState && ui.gameState.scores ? Object.keys(ui.gameState.scores) : [];
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
    if (ui.gameState && ui.gameState.ai_action && !humanWon && !result.is_draw) {
        const action = ui.gameState.ai_action;
        details += '\n\n';
        if (action.draw_from === 'discard' && action.drew_card) {
            details += `${opponentName} drew ${formatCardId(action.drew_card)} from discard pile`;
        } else {
            details += `${opponentName} drew from deck`;
        }
        details += ` and discarded ${formatCardId(action.discarded)}`;
    }

    // Add cumulative score display
    if (ui.gameState && ui.gameState.scores) {
        const humanScore = ui.gameState.scores[humanName] || 0;
        const opponentScore = ui.gameState.scores[opponentName] || 0;
        const targetInfo = ui.gameState.target_score ? ` / ${ui.gameState.target_score}` : '';
        details += `\n\nScore: ${humanName} ${humanScore}${targetInfo} - ${opponentName} ${opponentScore}${targetInfo}`;
    }

    // Append game/match winner info
    if (isMatchOver) {
        const gamesWon = ui.gameState.games_won || {};
        const p1Games = gamesWon[humanName] || 0;
        const p2Games = gamesWon[opponentName] || 0;
        details += `\n\n🏆 ${ui.gameState.match_winner} wins the match!\nFinal: ${humanName} ${p1Games} - ${p2Games} ${opponentName}`;
    } else if (isGameOver && isMatchMode) {
        const gamesWon = ui.gameState.games_won || {};
        const p1Games = gamesWon[humanName] || 0;
        const p2Games = gamesWon[opponentName] || 0;
        details += `\n\n🏆 ${ui.gameState.game_winner} wins this game!\nMatch: ${humanName} ${p1Games} - ${p2Games} ${opponentName}\nFirst to 2 wins the match.`;
    } else if (isGameOver) {
        details += `\n\n🏆 ${ui.gameState.game_winner} wins the game!`;
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

export function showGameOver(winner, scores, targetScore, matchMode, gamesWon, matchWinner) {
    // Hide round modal if it's showing
    elements.roundModal.classList.add('hidden');

    // Determine winner's score
    const winnerScore = scores[winner] || 0;
    const loserName = Object.keys(scores).find(name => name !== winner);
    const loserScore = scores[loserName] || 0;

    // Build game over details based on match mode
    if (matchMode && gamesWon) {
        const playerDisplayName = ui.gameState.player_name || savedSettings.playerName || 'Player';
        if (matchWinner) {
            // Match is complete
            elements.gameOverTitle.textContent = `🎉 Match Complete!`;
            const playerGames = gamesWon[ui.gameState.player_name] || 0;
            const aiGames = gamesWon['Computer'] || 0;
            elements.gameOverDetails.innerHTML = `
                <div style="text-align: center; padding: 20px;">
                    <p style="font-size: 1.5em; margin-bottom: 20px;">
                        <strong>${esc(matchWinner)}</strong> wins the match!
                    </p>
                    <div style="font-size: 1.2em; margin: 20px 0;">
                        <div style="margin: 10px 0;">
                            Match Score: ${esc(playerDisplayName)} ${playerGames} - ${aiGames} Computer
                        </div>
                    </div>
                </div>
            `;
        } else {
            // Game over but match continues
            const playerGames = gamesWon[ui.gameState.player_name] || 0;
            const aiGames = gamesWon['Computer'] || 0;
            elements.gameOverTitle.textContent = `Game Complete!`;
            elements.gameOverDetails.innerHTML = `
                <div style="text-align: center; padding: 20px;">
                    <p style="font-size: 1.5em; margin-bottom: 20px;">
                        <strong>${esc(winner)}</strong> wins this game!
                    </p>
                    <div style="font-size: 1.2em; margin: 20px 0;">
                        <div style="margin: 10px 0;">
                            Match Score: ${esc(playerDisplayName)} ${playerGames} - ${aiGames} Computer
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
                    <strong>${esc(winner)}</strong> reached ${targetScore} points!
                </p>
                <div style="font-size: 1.2em; margin: 20px 0;">
                    <div style="margin: 10px 0;">
                        <strong>${esc(winner)}:</strong> ${winnerScore} points
                    </div>
                    <div style="margin: 10px 0;">
                        <strong>${esc(loserName)}:</strong> ${loserScore} points
                    </div>
                </div>
            </div>
        `;
        elements.newGameAfterWinBtn.textContent = 'New Game';
    }

    // Show game over modal
    elements.gameOverModal.classList.remove('hidden');
}

// Show the resume prompt modal with the most recent resumable game
export function showResumePrompt(games) {
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
    } catch { /* ignore */ }

    const scoreInfo = game.target_score
        ? `${game.p1_score} / ${game.target_score} - ${game.p2_score} / ${game.target_score}`
        : `${game.p1_score} - ${game.p2_score}`;

    const settings = [];
    if (game.ai_difficulty) settings.push(game.ai_difficulty.charAt(0).toUpperCase() + game.ai_difficulty.slice(1) + ' AI');
    if (game.oklahoma_gin) settings.push('Oklahoma Gin');
    if (game.match_mode) settings.push('Match Play');

    elements.resumeGameDetails.innerHTML = `
        <div><span class="resume-detail-label">Players:</span> <span class="resume-detail-value">${esc(game.player1_name)} vs ${esc(game.player2_name)}</span></div>
        <div><span class="resume-detail-label">Score:</span> <span class="resume-detail-value">${scoreInfo}</span></div>
        <div><span class="resume-detail-label">Hands played:</span> <span class="resume-detail-value">${game.hand_count}</span></div>
        ${timeAgo ? `<div><span class="resume-detail-label">Started:</span> <span class="resume-detail-value">${timeAgo}</span></div>` : ''}
        ${settings.length > 0 ? `<div><span class="resume-detail-label">Settings:</span> <span class="resume-detail-value">${settings.join(', ')}</span></div>` : ''}
    `;

    // Store game ID for the resume button handler
    elements.resumeYesBtn.dataset.gameId = game.game_id;

    elements.resumeModal.classList.remove('hidden');
}
