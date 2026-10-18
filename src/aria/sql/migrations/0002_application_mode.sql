-- Persist the explicit installation mode and whether fictional demo fixtures ran.
CREATE TABLE application_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL CHECK (mode IN ('demo', 'personal')),
    demo_seeded INTEGER NOT NULL DEFAULT 0 CHECK (demo_seeded IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
