-- Fictional demo account; the database records that this seed ran exactly once.
INSERT INTO account_profiles (
    account_size,
    risk_fraction,
    leverage,
    account_currency,
    created_at,
    updated_at,
    last_confirmed_at 
) 
SELECT 
    1000000,
    0.1,
    10,
    "USD",
    datetime('now'),
    datetime('now'),
    datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM account_profiles);
-- Fictional demo instrument specifications for development and testing.
-- Futures margin and commission are illustrative sizing assumptions, not live broker data.
INSERT INTO instruments (
    symbol,
    name,
    instrument_type,
    base_currency,
    quote_currency,
    pip_size,
    whole_units,
    is_active
) VALUES (
    'USDJPY',
    'US Dollar / Japanese Yen',
    'forex',
    'USD',
    'JPY',
    0.01,
    1,
    1
)
ON CONFLICT(symbol) DO NOTHING;

INSERT INTO instruments (
    symbol,
    name,
    instrument_type,
    base_currency,
    quote_currency,
    contract_multiplier,
    tick_size,
    initial_margin_quote,
    commission_round_turn_quote,
    slippage_ticks,
    max_margin_fraction,
    exchange,
    is_active
) VALUES (
    'MES',
    'Micro E-mini S&P 500',
    'futures',
    NULL,
    'USD',
    5.0,
    0.25,
    1500.0,
    1.24,
    1,
    0.5,
    'CME',
    1
)
ON CONFLICT(symbol) DO NOTHING;
