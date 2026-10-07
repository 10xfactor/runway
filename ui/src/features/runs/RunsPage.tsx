import { GitCompare, Play, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Beacon, Button, EmptyState, Label, Sparkline } from "@/components/ui";
import { api } from "@/lib/api";
import { duration, usd } from "@/lib/format";
import { RUN_STYLE } from "@/lib/status";
import type { RunSummary } from "@/lib/types";

export function RunsPage() {
  const nav = useNavigate();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [status, setStatus] = useState("all");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    const pull = () => api.runs().then((r) => live && (setRuns(r), setErr(null))).catch((e) => live && setErr(String(e.message ?? e)));
    void pull();
    const t = setInterval(pull, 3000);
    return () => { live = false; clearInterval(t); };
  }, []);

  const shown = useMemo(() => (runs ?? []).filter((r) => status === "all" || r.status === status), [runs, status]);
  const costs = useMemo(() => [...(runs ?? [])].reverse().slice(-30).map((r) => r.totals.cost_usd), [runs]);
  const demo = async (failAt?: string) => { setBusy(true); try { nav(`/runs/${await api.demoStart(failAt)}`); } catch (e) { setErr(String((e as Error).message)); setBusy(false); } };

  if (err && !runs) return <div className="p-10"><div role="alert" className="mx-auto max-w-lg rounded-md border border-bad/40 bg-bad/5 p-5 text-bad"><TriangleAlert className="mb-2" />Cannot reach the Runway server: {err}<p className="mt-2 text-xs text-fg3">Open the URL printed by `runway dev` (it includes the session token).</p></div></div>;
  if (!runs) return <div className="p-10 text-fg3">Loading runs...</div>;

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <div className="mb-6 flex items-end justify-between">
        <div><Label>Runway Console</Label><h1 className="text-2xl font-semibold">Runs</h1></div>
        <div className="flex items-center gap-2">
          <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-sm border border-line-strong bg-raised px-2 py-1.5 text-xs">
            <option value="all">All statuses</option>{Object.keys(RUN_STYLE).map((s) => <option key={s} value={s}>{RUN_STYLE[s as keyof typeof RUN_STYLE].label}</option>)}
          </select>
          <Button disabled={picked.length !== 2} onClick={() => nav(`/compare?a=${picked[0]}&b=${picked[1]}`)}><GitCompare size={13} />Compare ({picked.length}/2)</Button>
          <Button variant="primary" disabled={busy} onClick={() => demo()}><Play size={13} />Run offline demo</Button>
        </div>
      </div>

      {runs.length === 0 ? (
        <EmptyState title="Nothing has run yet" action={<div className="flex gap-2"><Button variant="primary" onClick={() => demo()}><Play size={13} />Run the offline demo</Button><Button onClick={() => demo("report")}>Demo with a failing task</Button></div>}>
          The demo needs no API key. Watch a model get rejected by a deterministic validator, repair its output, and commit only what passes.
          <code className="mono mt-3 block rounded-sm border border-line bg-panel px-3 py-2 text-left text-xs text-fg2">pip install "runway-ai[ui]"<br />runway demo &amp;&amp; runway dev</code>
        </EmptyState>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-3 text-xs text-fg3"><Label>Cost per run</Label><Sparkline values={costs} /></div>
          <div className="overflow-hidden rounded-md border border-line">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-panel"><tr className="text-fg3">
                {["", "Status", "Run", "Graph", "Tasks", "Retries", "Cost", "Tokens", "Duration"].map((h) => <th key={h} className="label px-4 py-2.5 font-semibold">{h}</th>)}
              </tr></thead>
              <tbody>
                {shown.map((r) => {
                  const s = RUN_STYLE[r.status];
                  return (
                    <tr key={r.run_id} className="border-t border-line hover:bg-panel">
                      <td className="px-4 py-2.5"><input aria-label={`Select ${r.run_id}`} type="checkbox" checked={picked.includes(r.run_id)} onChange={(e) => setPicked((p) => e.target.checked ? [...p.slice(-1), r.run_id] : p.filter((x) => x !== r.run_id))} /></td>
                      <td className="px-4 py-2.5"><span className="inline-flex items-center gap-2" style={{ color: s.color }}><Beacon color={s.color} glow pulse={s.live ? "pulse" : ""} />{s.label}</span></td>
                      <td className="mono px-4 py-2.5"><Link className="hover:underline" to={`/runs/${r.run_id}`}>{r.run_id}</Link>{r.parent_run_id && <span className="ml-2 text-[10px] text-cache">replay</span>}</td>
                      <td className="px-4 py-2.5 text-fg2">{r.graph_id}</td>
                      <td className="px-4 py-2.5"><div className="flex items-center gap-2"><div className="flex h-1.5 w-20 overflow-hidden rounded-full bg-line"><span className="bg-ok" style={{ width: `${(r.tasks_ok / Math.max(r.tasks_total, 1)) * 100}%` }} /><span className="bg-bad" style={{ width: `${(r.tasks_failed / Math.max(r.tasks_total, 1)) * 100}%` }} /></div><span className="mono text-xs text-fg3">{r.tasks_ok}/{r.tasks_total}</span></div></td>
                      <td className="mono px-4 py-2.5 text-fg2">{r.retries}</td>
                      <td className="mono px-4 py-2.5">{usd(r.totals.cost_usd)}</td>
                      <td className="mono px-4 py-2.5 text-fg2">{Math.round(r.totals.tokens)}</td>
                      <td className="mono px-4 py-2.5 text-fg2">{r.totals.duration_ms ? duration(r.totals.duration_ms) : "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
