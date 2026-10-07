import * as Dialog from "@radix-ui/react-dialog";
import { History, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Chip, Label } from "@/components/ui";
import { Dag } from "@/features/console/Dag";
import { api } from "@/lib/api";
import { usd } from "@/lib/format";
import type { Graph, ReplayPlan, TaskState } from "@/lib/types";

export function ReplayStudio({ runId, snapGraph, tasks, onClose }: { runId: string; snapGraph: Graph; tasks: Record<string, TaskState>; onClose: () => void }) {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const names = snapGraph.nodes.map((n) => n.name);
  const initial = params.get("from") ?? Object.entries(tasks).find(([, t]) => t.status === "FAILED")?.[0] ?? names[names.length - 1] ?? "";
  const [from, setFrom] = useState(initial);
  const [plan, setPlan] = useState<ReplayPlan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [allowStale, setAllowStale] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setErr(null);
    api.replayPlan(runId, from).then(setPlan).catch((e) => { setPlan(null); setErr(String(e.message ?? e)); });
  }, [runId, from]);

  const overlay = useMemo(() => {
    if (!plan) return undefined;
    const o: Record<string, { kind: "reuse" | "rerun" | "stale"; note?: string }> = {};
    plan.reuse.forEach((n) => (o[n] = { kind: "reuse", note: "reused - no model call" }));
    plan.rerun.forEach((n) => (o[n] = { kind: "rerun", note: n === plan.from_task ? "restart here" : "downstream" }));
    plan.stale.forEach((s) => (o[s.task] = { kind: "stale", note: s.reason }));
    return o;
  }, [plan]);
  const blocked = !!plan?.stale.length && !allowStale;

  const start = async () => {
    setBusy(true);
    try { nav(`/runs/${await api.replayStart(runId, from, allowStale)}`); } catch (e) { setErr(String((e as Error).message)); setBusy(false); }
  };

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-tarmac/80 backdrop-blur-sm" />
        <Dialog.Content className="fixed inset-6 z-50 flex flex-col overflow-hidden rounded-md border border-line-strong bg-panel shadow-2xl outline-none" aria-describedby={undefined}>
          <header className="flex items-center justify-between border-b border-line px-5 py-3">
            <div className="flex items-center gap-3"><History size={18} className="text-cache" /><Dialog.Title className="text-base font-semibold">Replay Studio</Dialog.Title><Chip>{runId}</Chip></div>
            <Dialog.Close aria-label="Close" className="rounded p-1 text-fg3 hover:bg-raised hover:text-fg"><X size={16} /></Dialog.Close>
          </header>
          <div className="flex min-h-0 flex-1">
            <div className="min-w-0 flex-1"><Dag graph={snapGraph} tasks={tasks} selected={from} onSelect={(n) => n && setFrom(n)} overlay={overlay} minimap={false} /></div>
            <aside className="flex w-[360px] flex-col gap-5 border-l border-line p-5">
              <div><Label>Restart from</Label><div className="mt-1 text-lg font-semibold">{from}</div><p className="mt-1 text-xs text-fg3">Click a node to change the restart point. The original run is never modified: replay creates a child run.</p></div>
              {plan && (
                <div className="rounded-md border border-line bg-tarmac p-4">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div><div className="mono text-2xl font-semibold text-cache">{plan.reuse.length}</div><Label>Reuse</Label></div>
                    <div><div className="mono text-2xl font-semibold text-run">{plan.rerun.length}</div><Label>Re-run</Label></div>
                    <div><div className="mono text-2xl font-semibold" style={{ color: plan.stale.length ? "var(--color-bad)" : "var(--color-fg3)" }}>{plan.stale.length}</div><Label>Stale</Label></div>
                  </div>
                  <div className="mono mt-3 border-t border-line pt-3 text-center text-xs text-fg2">Estimated cost: up to {usd(plan.estimated_cost_usd_max)} - fresh budget</div>
                </div>
              )}
              {plan && plan.stale.length > 0 && (
                <div role="alert" className="rounded-sm border border-bad/40 bg-bad/5 p-3 text-xs">
                  <div className="mb-1 font-semibold text-bad">Upstream tasks changed since the original run</div>
                  <ul className="space-y-0.5 text-fg2">{plan.stale.map((s) => <li key={s.task}><b>{s.task}</b>: {s.reason}</li>)}</ul>
                  <label className="mt-2 flex items-center gap-2 text-fg2"><input type="checkbox" checked={allowStale} onChange={(e) => setAllowStale(e.target.checked)} />Allow stale: re-run these tasks too</label>
                </div>
              )}
              {err && <div role="alert" className="text-xs text-bad">{err}</div>}
              <Button variant="primary" disabled={!plan || blocked || busy} onClick={start} className="mt-auto justify-center py-2.5"><History size={14} />{busy ? "Starting..." : "Start replay"}</Button>
            </aside>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
