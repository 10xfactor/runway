// ponytail: hand-mirrored from runway.core.snapshot / events. Ceiling: drift. Upgrade path: generate from
// `runway events-schema` + OpenAPI. Drift is caught by reducer.test.ts running the golden fixtures.

export type TaskStatus =
  | "PENDING" | "READY" | "RUNNING" | "VALIDATING" | "REPAIRING"
  | "COMMITTED" | "CACHED" | "FAILED" | "SKIPPED";
export type RunStatus = "CREATED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED" | "BUDGET_EXCEEDED" | "AWAITING_HUMAN";

export interface Issue { code: string; path: string; message: string; hint: string; severity: string }
export interface Attempt {
  n: number; kind: string; outcome: "in_flight" | "accepted" | "rejected" | "error" | "aborted";
  tokens: number; cost_usd: number; latency_ms: number; issue_count: number; issues: Issue[];
  proposal_artifact_id: string | null; feedback_artifact_id: string | null; proposal_fingerprint: string;
  feedback_preview?: string; feedback_text?: string;
}
export interface TaskState {
  status: TaskStatus; attempts: Attempt[]; cache_key: string | null; cache_components: Record<string, string>;
  from_run_id: string | null; artifact_id: string | null; error_code: string | null;
  tokens: number; cost_usd: number; duration_ms: number; started_ts: string | null;
}
export interface GraphNode {
  name: string; model: string; input_contract: string; output_contract: string; validators: string[][]; max_retries: number;
}
export interface Graph { nodes: GraphNode[]; edges: { source: string; target: string }[] }
export interface RunInfo {
  run_id: string; graph_id: string; graph_hash: string; entrypoint: string | null; input_artifact_id: string;
  parent_run_id: string | null; replay_from: string | null; status: RunStatus;
  started_at: string | null; ended_at: string | null; created_at: string | null; error_code: string | null;
}
export interface Meter { used: number; limit: number | null }
export interface Snapshot {
  seq: number; run: RunInfo; graph: Graph | Record<string, never>;
  tasks: Record<string, TaskState>;
  totals: { tokens: number; cost_usd: number; duration_ms: number };
  budget: Record<string, Meter>;
  breach: { scope: string; dimension: string; used: number; limit: number; task: string | null } | null;
}
export interface RunEvent {
  run_id: string; seq: number; ts: string; type: string; schema_version: number;
  task_name: string | null; attempt_no: number | null; parent_seq: number | null;
  data: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
}
export interface RunSummary {
  run_id: string; graph_id: string; status: RunStatus; created_at: string | null; started_at: string | null;
  ended_at: string | null; parent_run_id: string | null; replay_from: string | null;
  totals: { tokens: number; cost_usd: number; duration_ms: number };
  tasks_ok: number; tasks_total: number; tasks_failed: number; retries: number; error_code: string | null;
}
export interface ReplayPlan {
  from_task: string; reuse: string[]; rerun: string[]; stale: { task: string; reason: string }[];
  estimated_cost_usd_max: number;
}
export interface CompareResult {
  a: RunSummary; b: RunSummary;
  tasks: { task: string; a: TaskBrief | null; b: TaskBrief | null; same_output: boolean }[];
}
export interface TaskBrief { status: TaskStatus; attempts: number; cost_usd: number; duration_ms: number }
export interface AttemptDiff {
  available: boolean; changes: { path: string; change: "added" | "removed" | "changed"; old?: unknown; new?: unknown }[];
  fixed_paths?: string[]; still_failing_paths?: string[]; new_failing_paths?: string[];
}
