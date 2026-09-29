"""The SQLite schema and its version."""

from __future__ import annotations

SCHEMA_VERSION = 4

SCHEMA = """
-- Track schema version for future migrations
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY
);

-- Individual games (a game consists of multiple hands until someone wins)
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    player1_name TEXT NOT NULL,
    player2_name TEXT NOT NULL,
    oklahoma_gin INTEGER DEFAULT 0,
    spade_doubling INTEGER DEFAULT 0,
    game_mode TEXT,
    target_score INTEGER,
    ai_difficulty TEXT,
    match_mode INTEGER DEFAULT 0,
    match_id INTEGER,
    winner_name TEXT,
    final_score_p1 INTEGER,
    final_score_p2 INTEGER,
    is_complete INTEGER DEFAULT 0
);

-- Individual hands within a game
CREATE TABLE IF NOT EXISTS hands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    hand_number INTEGER NOT NULL,
    dealer_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    winner_name TEXT,
    points_awarded INTEGER,
    is_gin INTEGER DEFAULT 0,
    is_undercut INTEGER DEFAULT 0,
    is_draw INTEGER DEFAULT 0,
    FOREIGN KEY (game_id) REFERENCES games(id)
);

-- Individual turns within a hand
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hand_id INTEGER NOT NULL,
    turn_number INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    drew_from TEXT NOT NULL,  -- 'deck' or 'discard'
    card_drawn TEXT NOT NULL,
    card_discarded TEXT,
    did_knock INTEGER DEFAULT 0,
    cards_before TEXT NOT NULL,  -- JSON array of cards
    cards_after TEXT NOT NULL,   -- JSON array of cards
    deadwood_before INTEGER NOT NULL,
    deadwood_after INTEGER NOT NULL,
    FOREIGN KEY (hand_id) REFERENCES hands(id)
);

-- AI decision reasoning (optional detailed tracking)
CREATE TABLE IF NOT EXISTS ai_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL,
    decision_type TEXT NOT NULL,  -- 'draw', 'discard', 'knock'
    choice TEXT NOT NULL,         -- what was chosen
    reasoning TEXT,               -- why it was chosen
    options_considered TEXT,      -- JSON array of alternatives
    FOREIGN KEY (turn_id) REFERENCES turns(id)
);

-- Lifetime player statistics
CREATE TABLE IF NOT EXISTS player_stats (
    player_name TEXT PRIMARY KEY,
    -- Hand outcomes
    total_hands INTEGER DEFAULT 0,
    hands_won INTEGER DEFAULT 0,
    hands_lost INTEGER DEFAULT 0,
    hands_drawn INTEGER DEFAULT 0,
    -- Special outcomes
    gins INTEGER DEFAULT 0,                    -- Times went gin
    undercuts_made INTEGER DEFAULT 0,          -- Times undercut opponent
    undercuts_suffered INTEGER DEFAULT 0,      -- Times got undercut
    -- Knocking stats
    times_knocked INTEGER DEFAULT 0,           -- Times this player knocked
    times_opponent_knocked INTEGER DEFAULT 0,  -- Times opponent knocked
    -- Scoring
    total_points_scored INTEGER DEFAULT 0,
    total_deadwood INTEGER DEFAULT 0,          -- Sum of all final deadwoods
    deadwood_count INTEGER DEFAULT 0,          -- Number of times deadwood was recorded
    -- Draw source preference
    draws_from_deck INTEGER DEFAULT 0,
    draws_from_discard INTEGER DEFAULT 0,
    -- Knock threshold
    total_knock_deadwood INTEGER DEFAULT 0,    -- Sum of deadwood when knocking
    knock_count INTEGER DEFAULT 0,             -- Number of times knocked (for avg)
    -- Metadata
    last_updated TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_hands_game_id ON hands(game_id);
CREATE INDEX IF NOT EXISTS idx_turns_hand_id ON turns(hand_id);
CREATE INDEX IF NOT EXISTS idx_turns_knock_stats ON turns(did_knock, player_name);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_turn_id ON ai_decisions(turn_id);
CREATE INDEX IF NOT EXISTS idx_games_started_at ON games(started_at);
"""
