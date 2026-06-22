-- iMouse Farm Database Schema
-- SQLite schema for multi-device orchestration state

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT,
    group_name TEXT DEFAULT 'default',
    model TEXT,
    ios_version TEXT,
    screen_width INTEGER,
    screen_height INTEGER,
    is_online INTEGER DEFAULT 0,
    current_state TEXT DEFAULT 'DISCONNECTED',
    last_seen_at TEXT,
    last_action TEXT,
    workflow_name TEXT,
    error_count INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    captured_at TEXT DEFAULT (datetime('now')),
    workflow_id TEXT,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_screenshots_device ON screenshots(device_id);
CREATE INDEX IF NOT EXISTS idx_screenshots_captured ON screenshots(captured_at);

CREATE TABLE IF NOT EXISTS state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT,
    transitioned_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_state_transitions_device ON state_transitions(device_id);

CREATE TABLE IF NOT EXISTS action_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    params_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    workflow_id TEXT,
    step_name TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    duration_ms INTEGER,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_action_history_device ON action_history(device_id);
CREATE INDEX IF NOT EXISTS idx_action_history_started ON action_history(started_at);

CREATE TABLE IF NOT EXISTS error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    escalated INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_error_logs_device ON error_logs(device_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_created ON error_logs(created_at);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name TEXT NOT NULL,
    device_id TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    iteration INTEGER DEFAULT 0,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_device ON workflow_runs(device_id);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    level TEXT NOT NULL DEFAULT 'info',
    category TEXT NOT NULL DEFAULT 'system',
    message TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON activity_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_activity_logs_device ON activity_logs(device_id);
