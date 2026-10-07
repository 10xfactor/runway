CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  graph_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  parent_run_id TEXT,
  snapshot_json TEXT NOT NULL
);
CREATE INDEX idx_runs_created ON runs(created_at DESC);

CREATE TABLE events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  task_name TEXT,
  attempt_no INTEGER,
  parent_seq INTEGER,
  schema_version INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);
CREATE INDEX idx_events_type ON events(run_id, type);
