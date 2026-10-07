// Pure reducer: must stay in sync with runway/core/snapshot.py (proved by reducer.test.ts on golden fixtures).
import type { Attempt, RunEvent, Snapshot, TaskState } from "./types";

export const emptyTask = (): TaskState => ({
  status: "PENDING", attempts: [], cache_key: null, cache_components: {}, from_run_id: null, artifact_id: null,
  error_code: null, tokens: 0, cost_usd: 0, duration_ms: 0, started_ts: null,
});

export function initialSnapshot(runId: string): Snapshot {
  return {
    seq: 0,
    run: {
      run_id: runId, graph_id: "", graph_hash: "", entrypoint: null, input_artifact_id: "", parent_run_id: null,
      replay_from: null, status: "CREATED", started_at: null, ended_at: null, created_at: null, error_code: null,
    },
    graph: {}, tasks: {}, totals: { tokens: 0, cost_usd: 0, duration_ms: 0 }, budget: {}, breach: null,
  };
}

export function applyEvent(prev: Snapshot, ev: RunEvent): Snapshot {
  return reduceInto(structuredClone(prev), ev);
}

/** Fold many events with a single clone (O(events), not O(events x snapshot)). */
export function applyEvents(prev: Snapshot, evs: RunEvent[]): Snapshot {
  const s = structuredClone(prev);
  for (const ev of evs) reduceInto(s, ev);
  return s;
}

function reduceInto(s: Snapshot, ev: RunEvent): Snapshot {
  const d = ev.data;
  s.seq = ev.seq;
  switch (ev.type) {
    case "run.created": {
      s.run = {
        run_id: ev.run_id, graph_id: d.graph_id, graph_hash: d.graph_hash, entrypoint: d.entrypoint ?? null,
        input_artifact_id: d.input_artifact_id, parent_run_id: d.parent_run_id ?? null, replay_from: d.replay_from ?? null,
        status: "CREATED", started_at: null, ended_at: null, created_at: ev.ts, error_code: null,
      };
      s.graph = d.graph ?? {};
      s.tasks = Object.fromEntries(((d.graph?.nodes ?? []) as { name: string }[]).map((n) => [n.name, emptyTask()]));
      s.budget = {
        tokens: { used: 0, limit: d.budget?.max_tokens ?? null },
        cost_usd: { used: 0, limit: d.budget?.max_cost_usd ?? null },
      };
      return s;
    }
    case "run.started": s.run.status = "RUNNING"; s.run.started_at = ev.ts; return s;
    case "run.completed": case "run.failed":
      s.run.status = d.status; s.run.ended_at = ev.ts; s.run.error_code = d.error_code ?? null; s.totals = { ...d.totals };
      return s;
    case "run.cancelled": s.run.status = "CANCELLED"; s.run.ended_at = ev.ts; return s;
    case "budget.exceeded":
      s.breach = { scope: d.scope, dimension: d.dimension, used: d.used, limit: d.limit, task: ev.task_name };
      break;
  }
  const t = ev.task_name ? s.tasks[ev.task_name] : undefined;
  if (!t) return s;
  const att: Attempt | undefined = [...t.attempts].reverse().find((a) => a.n === ev.attempt_no);
  switch (ev.type) {
    case "task.ready": t.status = "READY"; break;
    case "task.started": t.status = "RUNNING"; t.cache_key = d.cache_key; t.started_ts = ev.ts; t.cache_components = d.cache_components; break;
    case "task.cached":
      t.status = "CACHED"; t.from_run_id = d.from_run_id; t.artifact_id = d.artifact_id; t.cache_key = d.cache_key;
      t.cache_components = d.cache_components; break;
    case "task.committed": t.status = "COMMITTED"; t.artifact_id = d.artifact_id; t.duration_ms = d.duration_ms; break;
    case "task.failed": t.status = "FAILED"; t.error_code = d.error_code; break;
    case "task.skipped": t.status = "SKIPPED"; break;
    case "attempt.started":
      t.attempts.push({
        n: ev.attempt_no ?? t.attempts.length + 1, kind: d.kind, outcome: "in_flight", tokens: 0, cost_usd: 0,
        latency_ms: 0, issue_count: 0, issues: [], proposal_artifact_id: null, feedback_artifact_id: null,
        proposal_fingerprint: "",
      });
      t.status = "RUNNING"; break;
    case "attempt.aborted": if (att) att.outcome = "aborted"; break;
    case "model.generated":
      if (att) {
        att.tokens = d.prompt_tokens + d.completion_tokens; att.cost_usd = d.cost_usd; att.latency_ms = d.latency_ms;
        att.proposal_artifact_id = d.proposal_artifact_id ?? null;
        t.tokens += att.tokens; t.cost_usd += att.cost_usd;
        s.totals.tokens += att.tokens; s.totals.cost_usd += att.cost_usd;
        if (s.budget.tokens) s.budget.tokens.used = s.totals.tokens;
        if (s.budget.cost_usd) s.budget.cost_usd.used = s.totals.cost_usd;
      }
      break;
    case "validation.started": t.status = "VALIDATING"; break;
    case "validation.passed": if (att) att.outcome = "accepted"; break;
    case "validation.failed":
      if (att) {
        att.outcome = "rejected";
        att.issues = (d.results as { issues: Attempt["issues"] }[]).flatMap((r) => r.issues);
        att.issue_count = att.issues.length; att.proposal_fingerprint = d.proposal_fingerprint ?? "";
      }
      break;
    case "validation.errored": if (att) att.outcome = "error"; break;
    case "agent.retry": {
      t.status = "REPAIRING";
      const prevAtt = [...t.attempts].reverse().find((a) => a.n === (ev.attempt_no ?? 0));
      if (prevAtt) prevAtt.feedback_artifact_id = d.feedback_artifact_id;
      break;
    }
  }
  return s;
}
