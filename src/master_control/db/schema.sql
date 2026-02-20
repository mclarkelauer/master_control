CREATE TABLE IF NOT EXISTS workload_state (
    name           TEXT PRIMARY KEY,
    workload_type  TEXT NOT NULL,
    run_mode       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'registered',
    pid            INTEGER,
    run_count      INTEGER NOT NULL DEFAULT 0,
    max_runs       INTEGER,
    last_started   TEXT,
    last_stopped   TEXT,
    last_heartbeat TEXT,
    last_error     TEXT,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workload_name  TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    exit_code      INTEGER,
    error_message  TEXT,
    duration_ms    INTEGER,
    FOREIGN KEY (workload_name) REFERENCES workload_state(name)
);

CREATE INDEX IF NOT EXISTS idx_run_history_workload
    ON run_history(workload_name, started_at DESC);
