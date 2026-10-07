import { ArrowLeft, ArrowDown, ArrowUp, Equal } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Label, TaskBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { duration, usd } from "@/lib/format";
import type { CompareResult, TaskBrief } from "@/lib/types";

function Delta({ a, b, fmt, lowerIsBetter = true }: { a: number; b: number; fmt: (n: number) => string; lowerIsBetter?: boolean }) {
  const d = b - a;
  const pct = a ? (d / a) * 100 : 0;
  const better = d === 0 ? null : lowerIsBetter ? d < 0 : d > 0;
  const color = better === null ? "var(--color-fg3)" : better ? "var(--color-ok)" : "var(--color-bad)";
  const I = d === 0 ? Equal : d > 0 ? ArrowUp : ArrowDown;
  return (
    <div className="flex items-center gap-2">
      <span className="mono text-fg2">{fmt(a)}</span><span className="text-fg3">to</span><span className="mono text-lg font-semibold">{fmt(b)}</span>
      <span className="inline-flex items-center gap-0.5 text-xs" style={{ color }}><I size={12} />{a ? `${Math.abs(pct).toFixed(0)}%` : ""}</span>
    </div>
  );
}

const Cell = ({ t }: { t: TaskBrief | null }) => t ? (
  <div className="flex items-center gap-3"><TaskBadge status={t.status} compact /><span className="mono text-xs text-fg2">{t.attempts} att</span><span className="mono text-xs text-fg2">{usd(t.cost_usd)}</span><span className="mono text-xs text-fg3">{duration(t.duration_ms)}</span></div>
) : <span className="text-fg3">-</span>;

export function ComparePage() {
  const [p] = useSearchParams();
  const [res, setRes] = useState<CompareResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [a, b] = [p.get("a"), p.get("b")];
  useEffect(() => { if (a && b) api.compare(a, b).then(setRes).catch((e) => setErr(String(e.message ?? e))); }, [a, b]);
  if (!a || !b) return <div className="p-10 text-fg2">Pick two runs on the <Link to="/" className="underline">Runs</Link> page to compare.</div>;
  if (err) return <div role="alert" className="p-10 text-bad">{err}</div>;
  if (!res) return <div className="p-10 text-fg3">Comparing...</div>;
  const [x, y] = [res.a, res.b];
  const ok = (r: typeof x) => r.tasks_ok / Math.max(r.tasks_total, 1) * 100;
  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <Link to="/" className="mb-4 inline-flex items-center gap-1.5 text-fg3 hover:text-fg"><ArrowLeft size={14} />Runs</Link>
      <Label>Compare</Label>
      <h1 className="mono mb-6 text-xl font-semibold">{x.run_id} <span className="text-fg3">vs</span> {y.run_id}</h1>
      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          ["Success", <Delta key="s" a={ok(x)} b={ok(y)} fmt={(n) => `${n.toFixed(0)}%`} lowerIsBetter={false} />],
          ["Cost", <Delta key="c" a={x.totals.cost_usd} b={y.totals.cost_usd} fmt={usd} />],
          ["Latency", <Delta key="l" a={x.totals.duration_ms} b={y.totals.duration_ms} fmt={duration} />],
          ["Retries", <Delta key="r" a={x.retries} b={y.retries} fmt={(n) => String(n)} />],
        ].map(([l, v]) => <div key={String(l)} className="rounded-md border border-line bg-panel p-4"><Label>{l}</Label><div className="mt-2">{v}</div></div>)}
      </div>
      <div className="overflow-hidden rounded-md border border-line">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-panel"><tr><th className="label px-4 py-2.5">Task</th><th className="label px-4 py-2.5">Run A</th><th className="label px-4 py-2.5">Run B</th><th className="label px-4 py-2.5">Output</th></tr></thead>
          <tbody>{res.tasks.map((t) => (
            <tr key={t.task} className="border-t border-line"><td className="px-4 py-2.5 font-medium">{t.task}</td><td className="px-4 py-2.5"><Cell t={t.a} /></td><td className="px-4 py-2.5"><Cell t={t.b} /></td>
              <td className="px-4 py-2.5 text-xs" style={{ color: t.same_output ? "var(--color-ok)" : "var(--color-run)" }}>{t.same_output ? "identical" : "differs"}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
