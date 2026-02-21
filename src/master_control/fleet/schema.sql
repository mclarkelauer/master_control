CREATE TABLE IF NOT EXISTS fleet_clients (
    name            TEXT PRIMARY KEY,
    host            TEXT NOT NULL,
    api_port        INTEGER NOT NULL DEFAULT 9100,
    status          TEXT NOT NULL DEFAULT 'unknown',
    last_seen       TEXT,
    cpu_percent     REAL,
    memory_used_mb  REAL,
    memory_total_mb REAL,
    disk_used_gb    REAL,
    disk_total_gb   REAL,
    deployed_version TEXT,
    deployed_at     TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fleet_workloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name     TEXT NOT NULL,
    workload_name   TEXT NOT NULL,
    workload_type   TEXT NOT NULL,
    run_mode        TEXT NOT NULL,
    status          TEXT NOT NULL,
    pid             INTEGER,
    run_count       INTEGER NOT NULL DEFAULT 0,
    last_started    TEXT,
    last_error      TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(client_name, workload_name),
    FOREIGN KEY (client_name) REFERENCES fleet_clients(name)
);

CREATE INDEX IF NOT EXISTS idx_fleet_workloads_client
    ON fleet_workloads(client_name);
