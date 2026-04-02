-- Rate schedules with effective dates
-- The correct rate depends on when the account was opened vs when processing runs
CREATE TABLE IF NOT EXISTS rate_schedules (
    schedule_id TEXT PRIMARY KEY,
    effective_date INTEGER NOT NULL,  -- YYYYMMDD format
    base_rate REAL NOT NULL,
    tier1_threshold REAL NOT NULL DEFAULT 10000,
    tier1_bonus REAL NOT NULL DEFAULT 0.0025,
    tier2_threshold REAL NOT NULL DEFAULT 50000,
    tier2_bonus REAL NOT NULL DEFAULT 0.005,
    type_c_modifier REAL NOT NULL DEFAULT 0.0,     -- Checking accounts
    type_s_modifier REAL NOT NULL DEFAULT 0.005,   -- Savings accounts
    type_m_modifier REAL NOT NULL DEFAULT 0.01     -- Money Market accounts
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('C', 'S', 'M')),
    status TEXT NOT NULL DEFAULT 'A' CHECK (status IN ('A', 'C', 'F', 'H')),
    balance REAL NOT NULL DEFAULT 0,
    interest_rate REAL NOT NULL DEFAULT 0,  -- Legacy field, some accounts override schedule
    last_update INTEGER NOT NULL DEFAULT 0,
    -- NEW COMPLEXITY FIELDS:
    open_date INTEGER NOT NULL DEFAULT 19900101,  -- YYYYMMDD - for account age calculation
    parent_account_id INTEGER DEFAULT NULL,        -- NULL = no parent, else process parent first
    rate_schedule_id TEXT DEFAULT 'STD_2020',      -- References rate_schedules table
    processing_wave INTEGER DEFAULT 1,             -- Wave 1 = no deps, Wave 2+ = has deps
    legacy_rate_flag TEXT DEFAULT 'N' CHECK (legacy_rate_flag IN ('Y', 'N'))
);

CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_accounts_balance ON accounts(balance);
CREATE INDEX IF NOT EXISTS idx_accounts_type ON accounts(account_type);
CREATE INDEX IF NOT EXISTS idx_accounts_parent ON accounts(parent_account_id);
CREATE INDEX IF NOT EXISTS idx_accounts_wave ON accounts(processing_wave);
CREATE INDEX IF NOT EXISTS idx_rate_schedule_date ON rate_schedules(effective_date);
