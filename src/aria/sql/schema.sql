-- Schema version 1. Keep schema changes in versioned migrations after this.
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL CHECK (version > 0),
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, 1);

CREATE TABLE IF NOT EXISTS account_profiles (
    id INTEGER PRIMARY KEY,
    account_size NUMERIC NOT NULL CHECK (account_size > 0),
    risk_fraction NUMERIC NOT NULL
        CHECK (risk_fraction > 0 AND risk_fraction <= 1),
    leverage NUMERIC NOT NULL CHECK (leverage >= 1),
    account_currency TEXT NOT NULL CHECK (length(trim(account_currency)) = 3),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL COLLATE NOCASE UNIQUE
        CHECK (length(trim(symbol)) > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    instrument_type TEXT NOT NULL
        CHECK (instrument_type IN ('forex', 'futures')),
    base_currency TEXT,
    quote_currency TEXT NOT NULL CHECK (length(trim(quote_currency)) = 3),

    -- Forex specifications. Conversion rates are trade-time inputs, not static data.
    pip_size REAL,
    whole_units INTEGER CHECK (whole_units IN (0, 1)),

    -- Futures contract and sizing assumptions.
    contract_multiplier REAL,
    tick_size REAL,
    initial_margin_quote REAL,
    commission_round_turn_quote REAL NOT NULL DEFAULT 0
        CHECK (commission_round_turn_quote >= 0),
    slippage_ticks INTEGER NOT NULL DEFAULT 0 CHECK (slippage_ticks >= 0),
    max_margin_fraction REAL NOT NULL DEFAULT 0.5
        CHECK (max_margin_fraction > 0 AND max_margin_fraction <= 1),
    exchange TEXT,

    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    CHECK (
        (instrument_type = 'forex'
            AND base_currency IS NOT NULL
            AND length(trim(base_currency)) = 3
            AND pip_size IS NOT NULL AND pip_size > 0
            AND whole_units IS NOT NULL)
        OR
        (instrument_type = 'futures'
            AND contract_multiplier IS NOT NULL AND contract_multiplier > 0
            AND tick_size IS NOT NULL AND tick_size > 0
            AND initial_margin_quote IS NOT NULL AND initial_margin_quote > 0)
    )
);
