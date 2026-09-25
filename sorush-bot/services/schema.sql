-- Sorush Bot Database Schema
-- SQLite with WAL mode

-- ============================================
-- USERS TABLE - Per-server user statistics
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    user_name TEXT,
    guild_name TEXT,
    -- Message Statistics
    messages INTEGER DEFAULT 0,
    chars_total INTEGER DEFAULT 0,
    n_words_count INTEGER DEFAULT 0,
    max_chars_msg INTEGER DEFAULT 0,
    words_total INTEGER DEFAULT 0,
    emojis_used INTEGER DEFAULT 0,
    attachments_sent INTEGER DEFAULT 0,
    links_shared INTEGER DEFAULT 0,
    replies_sent INTEGER DEFAULT 0,
    mentions_made INTEGER DEFAULT 0,
    -- Voice Statistics
    voice_mins INTEGER DEFAULT 0,
    max_call_time INTEGER DEFAULT 0,
    voice_sessions INTEGER DEFAULT 0,
    stream_mins INTEGER DEFAULT 0,
    muted_mins INTEGER DEFAULT 0,
    deafened_mins INTEGER DEFAULT 0,
    -- XP and Leveling
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    xp_from_messages INTEGER DEFAULT 0,
    xp_from_voice INTEGER DEFAULT 0,
    xp_from_reactions INTEGER DEFAULT 0,
    -- Reactions
    reactions_given INTEGER DEFAULT 0,
    reactions_received INTEGER DEFAULT 0,
    -- Activity Tracking
    commands_used INTEGER DEFAULT 0,
    games_played INTEGER DEFAULT 0,
    games_won INTEGER DEFAULT 0,
    -- Daily Activity
    daily_streak INTEGER DEFAULT 0,
    max_daily_streak INTEGER DEFAULT 0,
    last_daily_activity TEXT,
    active_days INTEGER DEFAULT 0,
    -- Economy
    mora INTEGER DEFAULT 0,
    mora_total_earned INTEGER DEFAULT 0,
    mora_total_spent INTEGER DEFAULT 0,
    last_daily_claim TEXT,
    daily_claim_streak INTEGER DEFAULT 0,
    max_daily_claim_streak INTEGER DEFAULT 0,
    gambling_wins INTEGER DEFAULT 0,
    gambling_losses INTEGER DEFAULT 0,
    gambling_profit INTEGER DEFAULT 0,
    gambling_daily_losses INTEGER DEFAULT 0,
    gambling_daily_reset TEXT,
    -- Timestamps
    first_message_at TEXT,
    first_voice_at TEXT,
    last_message_at TEXT,
    last_voice_at TEXT,
    last_interaction TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_users_guild ON users(guild_id);
CREATE INDEX IF NOT EXISTS idx_users_guild_user ON users(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_users_xp ON users(guild_id, xp DESC);
CREATE INDEX IF NOT EXISTS idx_users_messages ON users(guild_id, messages DESC);
CREATE INDEX IF NOT EXISTS idx_users_voice ON users(guild_id, voice_mins DESC);

-- ============================================
-- GUILD CONFIG TABLE (All server settings in one place)
-- ============================================
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    guild_name TEXT,
    prefix TEXT DEFAULT '!',
    -- Logging
    log_channel_id INTEGER,
    log_enabled INTEGER DEFAULT 0,
    log_events TEXT DEFAULT '{}',
    -- Welcome
    welcome_channel_id INTEGER,
    welcome_message TEXT,
    -- XP System
    xp_enabled INTEGER DEFAULT 1,
    xp_multiplier REAL DEFAULT 1.0,
    xp_message_amount INTEGER DEFAULT -1,
    xp_voice_amount INTEGER DEFAULT -1,
    xp_accumulate_roles INTEGER DEFAULT 1,
    xp_levelup_message INTEGER DEFAULT 1,
    xp_levelup_channel_id INTEGER,
    -- AutoRole
    autorole_id INTEGER,
    autorole_enabled INTEGER DEFAULT 0,
    -- Economy
    daily_base INTEGER DEFAULT 500,
    daily_streak_bonus INTEGER DEFAULT 50,
    daily_max_streak_bonus INTEGER DEFAULT 1000,
    -- Gambling
    gambling_enabled INTEGER DEFAULT 1,
    gambling_min_bet INTEGER DEFAULT 50,
    gambling_max_bet INTEGER DEFAULT 50000,
    gambling_daily_loss_limit INTEGER DEFAULT 10000,
    gambling_house_edge REAL DEFAULT 0.02,
    -- Shop
    shop_enabled INTEGER DEFAULT 1,
    -- Feature Toggles (server preferences / memory)
    feature_economy_enabled INTEGER DEFAULT 1,
    feature_fun_enabled INTEGER DEFAULT 1,
    feature_moderation_enabled INTEGER DEFAULT 1,
    feature_notifications_enabled INTEGER DEFAULT 1,
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- MOD LOGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS mod_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id)
);

CREATE INDEX IF NOT EXISTS idx_mod_logs_guild ON mod_logs(guild_id);
CREATE INDEX IF NOT EXISTS idx_mod_logs_user ON mod_logs(guild_id, user_id);

-- ============================================
-- XP ROLES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS xp_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    level_required INTEGER NOT NULL,
    UNIQUE(guild_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_xp_roles_guild ON xp_roles(guild_id);

-- ============================================
-- WARNINGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id, user_id);

-- ============================================
-- USER DAILY STATS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS user_daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    messages INTEGER DEFAULT 0,
    voice_mins INTEGER DEFAULT 0,
    xp_earned INTEGER DEFAULT 0,
    chars_total INTEGER DEFAULT 0,
    reactions_given INTEGER DEFAULT 0,
    commands_used INTEGER DEFAULT 0,
    UNIQUE(guild_id, user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON user_daily_stats(guild_id, user_id, date);

-- ============================================
-- USER ACHIEVEMENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS user_achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    achievement_id TEXT NOT NULL,
    achievement_name TEXT NOT NULL,
    earned_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, user_id, achievement_id)
);

CREATE INDEX IF NOT EXISTS idx_achievements_user ON user_achievements(guild_id, user_id);

-- ============================================
-- CHANNEL STATS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS channel_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    channel_name TEXT,
    channel_type TEXT,
    messages INTEGER DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    last_activity TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_stats ON channel_stats(guild_id, channel_id);

-- ============================================
-- COMMAND HISTORY TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    command_name TEXT NOT NULL,
    used_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_command_history ON command_history(guild_id, user_id);

-- ============================================
-- VOICE SESSIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS voice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_id INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_mins INTEGER DEFAULT 0,
    was_streaming INTEGER DEFAULT 0,
    was_muted INTEGER DEFAULT 0,
    was_deafened INTEGER DEFAULT 0,
    interrupted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_voice_sessions ON voice_sessions(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_voice_sessions_active ON voice_sessions(guild_id, ended_at) WHERE ended_at IS NULL;

-- ============================================
-- TRANSACTIONS TABLE (Economy/Mora)
-- ============================================
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    description TEXT,
    related_user_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(guild_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(guild_id, type);

-- ============================================
-- SHOP ITEMS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS shop_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    price INTEGER NOT NULL,
    duration_type TEXT DEFAULT 'temporary',
    duration_days INTEGER DEFAULT 7,
    condition TEXT,
    name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_shop_items_guild ON shop_items(guild_id);

-- ============================================
-- SHOP PURCHASES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS shop_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    duration_type TEXT DEFAULT 'temporary',
    condition TEXT,
    purchased_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_shop_purchases_guild ON shop_purchases(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_shop_purchases_expires ON shop_purchases(expires_at) WHERE expires_at IS NOT NULL;

-- ============================================
-- USER NOTIFICATIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS user_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, user_id, keyword)
);

CREATE INDEX IF NOT EXISTS idx_notifications_guild ON user_notifications(guild_id, user_id);
