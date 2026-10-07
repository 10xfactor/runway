import { applyEvents, initialSnapshot } from "./reducer";
import type { AttemptDiff, CompareResult, ReplayPlan, RunEvent, RunSummary, Snapshot, TaskState } from "./types";

export const EVENT_TYPES = [
  "run.created", "run.started", "run.completed", "run.failed", "run.cancelled", "task.ready", "task.started",
  "task.cached", "task.committed", "task.failed", "task.skipped", "attempt.started", "attempt.aborted",
  "model.requested", "model.generated", "validation.started", "validation.passed", "validation.failed",
  "validation.errored", "agent.retry", "artifact.created", "budget.warning", "budget.exceeded",
];

export type ConnState = "history" | "live" | "reconnecting" | "error";
export interface TaskDetail { task: string; state: TaskState; node: Record<string, unknown> }
export interface Health { version: string; payloads_exposed: boolean }

export interface Api {
  mock: boolean;
  health(): Promise<Health>;
  runs(): Promise<RunSummary[]>;
  events(runId: string, after: number): Promise<RunEvent[]>;
  stream(runId: string, after: number, onEvent: (e: RunEvent) => void, onState: (s: ConnState) => void): () => void;
  task(runId: string, task: string): Promise<TaskDetail>;
  diff(runId: string, task: string, n: number): Promise<AttemptDiff>;
  replayPlan(runId: string, fromTask: string): Promise<ReplayPlan>;
  replayStart(runId: string, fromTask: string, allowStale: boolean): Promise<string>;
  cancel(runId: string): Promise<void>;
  demoStart(failAt?: string): Promise<string>;
  compare(a: string, b: string): Promise<CompareResult>;
}

const TOKEN_KEY = "runway.token";
export function captureToken() {
  const m = /token=([^&]+)/.exec(location.hash);
  if (m) {
    sessionStorage.setItem(TOKEN_KEY, decodeURIComponent(m[1]!));
    history.replaceState(null, "", location.pathname + location.search);
  }
}
const token = () => sessionStorage.getItem(TOKEN_KEY) ?? "";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token()}`, "Content-Type": "application/json" },
  });
  if (!r.ok) throw new Error(`${r.status}: ${(await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText}`);
  return r.json() as Promise<T>;
}
const post = <T>(path: string, body?: unknown) => call<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const httpApi: Api = {
  mock: false,
  health: () => fetch("/api/health").then((r) => r.json()),
  runs: () => call("/runs?limit=200"),
  async events(runId, after) {
    const out: RunEvent[] = [];
    for (;;) {
      const page = await call<RunEvent[]>(`/runs/${runId}/events?after_seq=${after}&limit=5000`);
      out.push(...page);
      if (page.length < 5000) return out;
      after = page[page.length - 1]!.seq;
    }
  },
  stream(runId, after, onEvent, onState) {
    const es = new EventSource(`/api/runs/${runId}/stream?after=${after}&token=${encodeURIComponent(token())}`);
    const handler = (m: MessageEvent) => onEvent(JSON.parse(m.data));
    EVENT_TYPES.forEach((t) => es.addEventListener(t, handler as EventListener));
    es.addEventListener("stream.end", () => { es.close(); onState("history"); });
    es.onopen = () => onState("live");
    es.onerror = () => onState(es.readyState === EventSource.CLOSED ? "error" : "reconnecting");
    return () => es.close();
  },
  task: (r, t) => call(`/runs/${r}/tasks/${t}`),
  diff: (r, t, n) => call(`/runs/${r}/attempts/${t}/${n}/diff`),
  replayPlan: (r, t) => post(`/runs/${r}/replay/plan`, { from_task: t }),
  replayStart: async (r, t, allow) => (await post<{ child_run_id: string }>(`/runs/${r}/replay`, { from_task: t, allow_stale: allow })).child_run_id,
  cancel: async (r) => { await post(`/runs/${r}/cancel`); },
  demoStart: async (failAt) => (await post<{ run_id: string }>(`/demo/start${failAt ? `?fail_at=${encodeURIComponent(failAt)}` : ""}`)).run_id,
  compare: (a, b) => call(`/compare?a=${a}&b=${b}`),
};

// ---------------------------------------------------------------- mock mode (fixtures, no backend)
const raw = import.meta.glob("../../../fixtures/scenarios/*.jsonl", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const FIXTURES: Record<string, RunEvent[]> = {};
for (const [p, text] of Object.entries(raw)) {
  const name = p.split("/").pop()!.replace(".jsonl", "");
  FIXTURES[name] = text.trim().split("\n").map((l) => ({ ...JSON.parse(l), run_id: name }));
}
const speed = () => Number(new URLSearchParams(location.search).get("speed") ?? "1");
const fold = (name: string) => applyEvents(initialSnapshot(name), FIXTURES[name] ?? []);
const summarize = (s: Snapshot): RunSummary => ({
  run_id: s.run.run_id, graph_id: s.run.graph_id, status: s.run.status, created_at: s.run.created_at,
  started_at: s.run.started_at, ended_at: s.run.ended_at, parent_run_id: s.run.parent_run_id, replay_from: s.run.replay_from,
  totals: s.totals, tasks_ok: Object.values(s.tasks).filter((t) => t.status === "COMMITTED" || t.status === "CACHED").length,
  tasks_total: Object.keys(s.tasks).length, tasks_failed: Object.values(s.tasks).filter((t) => t.status === "FAILED").length,
  retries: Object.values(s.tasks).reduce((a, t) => a + Math.max(t.attempts.length - 1, 0), 0), error_code: s.run.error_code,
});
const tick = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const mockApi: Api = {
  mock: true,
  health: async () => ({ version: "mock", payloads_exposed: false }),
  runs: async () => Object.keys(FIXTURES).map((n) => summarize(fold(n))),
  events: async (runId, after) => {
    // Live scenarios: serve only the first event so the stream plays the rest.
    const live = new URLSearchParams(location.search).get("live") !== "0";
    const all = FIXTURES[runId] ?? [];
    return (live ? all.slice(0, 1) : all).filter((e) => e.seq > after);
  },
  stream(runId, after, onEvent, onState) {
    let stop = false;
    onState("live");
    (async () => {
      for (const ev of (FIXTURES[runId] ?? []).filter((e) => e.seq > Math.max(after, 1))) {
        if (stop) return;
        await tick((ev.type === "model.requested" ? 500 : 140) / speed());
        onEvent(ev);
      }
      onState("history");
    })();
    return () => { stop = true; };
  },
  task: async (runId, task) => ({ task, state: fold(runId).tasks[task]!, node: {} }),
  diff: async () => ({ available: false, changes: [] }),
  replayPlan: async (runId, from) => {
    const s = fold(runId);
    const names = Object.keys(s.tasks);
    const edges = (s.graph as { edges?: { source: string; target: string }[] }).edges ?? [];
    const down = new Set([from]);
    for (let i = 0; i < names.length; i++) edges.forEach((e) => down.has(e.source) && down.add(e.target));
    return { from_task: from, reuse: names.filter((n) => !down.has(n)), rerun: names.filter((n) => down.has(n)), stale: [], estimated_cost_usd_max: 2 };
  },
  replayStart: async () => "cached_replay",
  cancel: async () => {},
  demoStart: async () => "repair_then_pass",
  compare: async (a, b) => {
    const [sa, sb] = [fold(a), fold(b)];
    const brief = (t?: TaskState) => (t ? { status: t.status, attempts: t.attempts.length, cost_usd: t.cost_usd, duration_ms: t.duration_ms } : null);
    const names = [...new Set([...Object.keys(sa.tasks), ...Object.keys(sb.tasks)])].sort();
    return {
      a: summarize(sa), b: summarize(sb),
      tasks: names.map((n) => ({ task: n, a: brief(sa.tasks[n]), b: brief(sb.tasks[n]), same_output: !!sa.tasks[n]?.artifact_id && sa.tasks[n]?.artifact_id === sb.tasks[n]?.artifact_id })),
    };
  },
};

export const api: Api = import.meta.env.VITE_MOCK ? mockApi : httpApi;
