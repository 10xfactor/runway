import { AlertTriangle, ArrowLeft, Copy, History, Play, Square, WifiOff } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button, DigitRoll, Label, Meter, RunPill } from "@/components/ui";
import { Inspector } from "@/features/inspector/Inspector";
import { api } from "@/lib/api";
import { clock, compact, usd } from "@/lib/format";
import { topoOrder } from "@/lib/layout";
import { ACTIVE, OK, RUN_STYLE, isTerminalRun } from "@/lib/status";
import type { Graph } from "@/lib/types";
import { useRun } from "@/store/run";
import { ReplayStudio } from "@/features/replay/ReplayStudio";
import { Dag } from "./Dag";
import { Timeline } from "./Timeline";

function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { if (!active) return; const t = setInterval(() => setNow(Date.now()), 250); return () => clearInterval(t); }, [active]);
  return now;
}

function Gauge({ label, children, meter }: { label: string; children: React.ReactNode; meter?: React.ReactNode }) {
  return (
    <div className="flex min-w-[170px] flex-col gap-1.5 border-r border-line px-5 py-2.5 last:border-r-0">
      <Label>{label}</Label>
      <div className="text-xl font-semibold leading-none">{children}</div>
      {meter ?? <div className="h-3" />}
    </div>
  );
}

export function ConsolePage() {
  const params = useParams();
  const runId = params.runId ?? "";
  const rest = params["*"] ?? "";
  const task = rest.startsWith("tasks/") ? decodeURIComponent(rest.slice(6)) : undefined;
  const nav = useNavigate();
  const { snap, events, conn, error, follow, setFollow, load, close } = useRun();
  useEffect(() => { void load(runId); return close; }, [runId, load, close]);
  const selected = task ?? null;
  const select = (t: string | null) => nav(t ? `/runs/${runId}/tasks/${t}` : `/runs/${runId}`, { replace: true });
  const running = !!snap && !isTerminalRun(snap.run.status);
  const now = useNow(running);

  const graph = (snap?.graph ?? {}) as Graph;
  const order = useMemo(() => (graph.nodes ? topoOrder(graph) : []), [graph]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input,textarea,[cmdk-root]") || e.metaKey || e.ctrlKey) return;
      const i = selected ? order.indexOf(selected) : -1;
      if (e.key === "j") select(order[Math.min(i + 1, order.length - 1)] ?? null);
      if (e.key === "k") select(order[Math.max(i - 1, 0)] ?? null);
      if (e.key === "r") nav(`/runs/${runId}/replay${selected ? `?from=${selected}` : ""}`);
      if (e.key === "Escape") select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (error) return <div className="p-10 text-bad">Could not load run: {error}</div>;
  if (!snap) return <div className="p-10 text-fg3">Loading run...</div>;
  const r = snap.run, st = RUN_STYLE[r.status];
  const startMs = r.started_at ? Date.parse(r.started_at) : 0;
  const elapsed = r.ended_at ? snap.totals.duration_ms || Date.parse(r.ended_at) - startMs : startMs ? now - startMs : 0;
  const tasks = Object.values(snap.tasks);
  const retries = tasks.reduce((a, t) => a + Math.max(t.attempts.length - 1, 0), 0);
  const failed = tasks.find((t) => t.status === "FAILED");
  const activeCount = tasks.filter((t) => ACTIVE.includes(t.status)).length;

  return (
    <div className="flex h-full flex-col">
      <div className={`status-strip ${st.live ? "live" : ""}`} style={{ "--c": st.color } as React.CSSProperties} />
      <header className="flex items-center gap-4 border-b border-line bg-panel px-5 py-3">
        <Link to="/" aria-label="Back to runs" className="text-fg3 hover:text-fg"><ArrowLeft size={18} /></Link>
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="mono text-[15px] font-semibold">{r.run_id}</h1>
            <button aria-label="Copy run id" onClick={() => navigator.clipboard?.writeText(r.run_id)} className="text-fg3 hover:text-fg"><Copy size={13} /></button>
          </div>
          <div className="text-xs text-fg3">
            {r.graph_id}{r.parent_run_id && <> - replayed from <Link className="text-cache underline-offset-2 hover:underline" to={`/runs/${r.parent_run_id}`}>{r.parent_run_id}</Link> @ {r.replay_from}</>}
          </div>
        </div>
        <RunPill status={r.status} />
        <div className="mono ml-2 text-sm text-fg2">{clock(elapsed)}</div>
        <ConnPill conn={conn} />
        <div className="ml-auto flex gap-2">
          {running && <Button variant="danger" onClick={() => api.cancel(r.run_id).catch((e) => alert(String(e)))}><Square size={13} />Cancel</Button>}
          <Button variant={failed ? "primary" : "default"} onClick={() => nav(`/runs/${runId}/replay${failed ? `?from=${Object.entries(snap.tasks).find(([, t]) => t === failed)?.[0]}` : selected ? `?from=${selected}` : ""}`)}>
            <History size={13} />Replay<span className="ml-1 text-[10px] opacity-60">r</span>
          </Button>
        </div>
      </header>

      <section className="flex border-b border-line bg-panel/60" aria-label="Run totals">
        <Gauge label="Cost" meter={<Meter used={snap.budget.cost_usd?.used ?? 0} limit={snap.budget.cost_usd?.limit ?? null} />}>
          <DigitRoll value={usd(snap.totals.cost_usd)} /> <span className="text-xs font-normal text-fg3">/ {snap.budget.cost_usd?.limit != null ? usd(snap.budget.cost_usd.limit) : "no limit"}</span>
        </Gauge>
        <Gauge label="Tokens" meter={<Meter used={snap.budget.tokens?.used ?? 0} limit={snap.budget.tokens?.limit ?? null} />}>
          <DigitRoll value={compact(snap.totals.tokens)} /> <span className="text-xs font-normal text-fg3">/ {snap.budget.tokens?.limit != null ? compact(snap.budget.tokens.limit) : "no limit"}</span>
        </Gauge>
        <Gauge label="Time"><DigitRoll value={clock(elapsed)} /></Gauge>
        <Gauge label="Repairs"><DigitRoll value={String(retries)} /> <span className="text-xs font-normal text-fg3">retries</span></Gauge>
        <Gauge label="Tasks"><DigitRoll value={String(tasks.filter((t) => OK.includes(t.status)).length)} /> <span className="text-xs font-normal text-fg3">/ {tasks.length} done{activeCount ? ` - ${activeCount} active` : ""}</span></Gauge>
      </section>

      {snap.breach && (
        <div role="alert" className="flex items-center gap-2 border-b border-bad/40 bg-bad/10 px-5 py-2 text-xs text-bad">
          <AlertTriangle size={14} />Budget exceeded: {snap.breach.scope} {snap.breach.dimension} ({Math.round(snap.breach.used * 100) / 100} of {snap.breach.limit}){snap.breach.task && <> in <b>{snap.breach.task}</b></>}. The run was stopped deterministically.
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <main className="relative min-w-0 flex-1" aria-label="Work graph">
          {graph.nodes ? <Dag graph={graph} tasks={snap.tasks} selected={selected} onSelect={select} follow={follow && running} /> : null}
          <label className="absolute left-4 top-3 z-10 flex items-center gap-2 rounded-full border border-line bg-panel/90 px-3 py-1 text-[11px] text-fg2 backdrop-blur">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow active
          </label>
        </main>
        {selected && snap.tasks[selected] && (
          <Inspector runId={runId} task={selected} node={graph.nodes?.find((n) => n.name === selected)} state={snap.tasks[selected]!} events={events} onClose={() => select(null)} />
        )}
      </div>
      <Timeline events={events} selected={selected} onSelect={select} startTs={r.started_at} />
      {rest === "replay" && <ReplayStudio runId={runId} snapGraph={graph} tasks={snap.tasks} onClose={() => nav(`/runs/${runId}`)} />}
    </div>
  );
}

function ConnPill({ conn }: { conn: string }) {
  const map: Record<string, [string, string]> = { live: ["live", "var(--color-ok)"], history: ["history", "var(--color-fg3)"], reconnecting: ["reconnecting", "var(--color-run)"], error: ["disconnected", "var(--color-bad)"] };
  const [label, color] = map[conn] ?? map.history!;
  return <span className="inline-flex items-center gap-1.5 text-[11px]" style={{ color }}>{conn === "error" || conn === "reconnecting" ? <WifiOff size={12} /> : <Play size={10} />}{label}</span>;
}
