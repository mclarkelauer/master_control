CREATE TABLE IF NOT EXISTS deployments (
    id              TEXT PRIMARY KEY,
    version         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    batch_size      INTEGER NOT NULL DEFAULT 1,
    target_clients  TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    completed_at    TEXT,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS deployment_clients (
    deployment_id   TEXT NOT NULL,
    client_name     TEXT NOT NULL,
    batch_number    INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    previous_version TEXT,
    started_at      TEXT,
    completed_at    TEXT,
    error           TEXT,
    PRIMARY KEY (deployment_id, client_name),
    FOREIGN KEY (deployment_id) REFERENCES deployments(id)
);

CREATE INDEX IF NOT EXISTS idx_deployment_clients_deployment
    ON deployment_clients(deployment_id);
