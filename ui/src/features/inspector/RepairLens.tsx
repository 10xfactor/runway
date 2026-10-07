import clsx from "clsx";
import { ArrowDown, Equal, Minus, Plus, RefreshCw, Replace } from "lucide-react";
import { useEffect, useState } from "react";
import { Beacon, Chip, Label } from "@/components/ui";
import { api } from "@/lib/api";
import { previewFromIssues } from "@/lib/events";
import { compact, duration, usd } from "@/lib/format";
import type { Attempt, AttemptDiff, TaskState } from "@/lib/types";

const OUTCOME = {
  accepted: { c: "var(--color-ok)", t: "Accepted" }, rejected: { c: "var(--color-bad)", t: "Rejected" },
  error: { c: "var(--color-bad)", t: "Validator error" }, aborted: { c: "var(--color-idle)", t: "Aborted" },
  in_flight: { c: "var(--color-run)", t: "In flight" },
} as const;

const CHANGE = { added: { I: Plus, c: "var(--color-ok)" }, removed: { I: Minus, c: "var(--color-bad)" }, changed: { I: Replace, c: "var(--color-run)" } } as const;

function Diff({ runId, task, n, prev }: { runId: string; task: string; n: number; prev: Attempt }) {
  const [diff, setDiff] = useState<AttemptDiff | null>(null);
  const [mode, setMode] = useState<"changes" | "issues">("changes");
  useEffect(() => { api.diff(runId, task, n).then(setDiff).catch(() => setDiff({ available: false, changes: [] })); }, [runId, task, n]);
  if (!diff?.available) return null;
  const fixed = diff.fixed_paths ?? [], still = diff.still_failing_paths ?? [], fresh = diff.new_failing_paths ?? [];
  return (
    <div className="mt-3 rounded-sm border border-line bg-tarmac p-2.5">
      <div className="mb-2 flex items-center gap-2">
        <Label>vs attempt {n - 1}</Label>
        {prev.issue_count > 0 && (
          <Chip color={still.length || fresh.length ? "var(--color-run)" : "var(--color-ok)"}>issues fixed {fixed.length} of {prev.issue_count}</Chip>
        )}
        <div className="ml-auto flex gap-1">
          {(["changes", "issues"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)} className={clsx("rounded-full border px-2 py-0.5 text-[10px] capitalize", mode === m ? "border-fg3 text-fg" : "border-line text-fg3")}>{m}</button>
          ))}
        </div>
      </div>
      {mode === "changes" ? (
        <ul className="mono space-y-1 text-[12px]">
          {diff.changes.length === 0 && <li className="flex items-center gap-1.5 text-fg3"><Equal size={12} /> identical output</li>}
          {diff.changes.map((c) => {
            const { I, c: color } = CHANGE[c.change];
            const bad = still.includes(c.path) || fresh.includes(c.path);
            return (
              <li key={c.path} className="flex items-center gap-2">
                <I size={12} style={{ color }} aria-label={c.change} />
                <span className={clsx(bad ? "text-bad underline decoration-bad/50 underline-offset-2" : fixed.includes(c.path) ? "text-ok" : "text-fg2")}>{c.path}</span>
                {"old" in c && <span className="truncate text-fg3">{JSON.stringify(c.old)} <span className="text-fg2">to</span> {JSON.stringify(c.new)}</span>}
                {fixed.includes(c.path) && <span className="text-[10px] text-ok">fixed</span>}
                {bad && <span className="text-[10px] text-bad">still failing</span>}
              </li>
            );
          })}
        </ul>
      ) : (
        <ul className="mono space-y-1 text-[12px]">
          {fixed.map((p) => <li key={p} className="text-ok">fixed {p}</li>)}
          {still.map((p) => <li key={p} className="text-bad">still failing {p}</li>)}
          {fresh.map((p) => <li key={p} className="text-bad">new failure {p}</li>)}
        </ul>
      )}
    </div>
  );
}

export function RepairLens({ runId, task, state, feedbackText }: { runId: string; task: string; state: TaskState; feedbackText: Record<number, string> }) {
  const atts = state.attempts;
  if (!atts.length) return <p className="text-fg3">No attempts yet.</p>;
  return (
    <ol className="space-y-0">
      {atts.map((a, i) => {
        const o = OUTCOME[a.outcome];
        const next = atts[i + 1];
        return (
          <li key={a.n}>
            <div className="rounded-md border border-line bg-panel p-3" style={{ borderColor: `color-mix(in srgb, ${o.c} 35%, var(--color-line))` }}>
              <div className="flex items-center gap-2">
                <Beacon color={o.c} glow pulse={a.outcome === "in_flight" ? "pulse" : ""} />
                <span className="font-semibold">Attempt {a.n}</span>
                <Chip>{a.kind}</Chip>
                <span className="ml-auto text-xs font-semibold" style={{ color: o.c }}>{o.t}</span>
              </div>
              <div className="mono mt-1.5 flex gap-3 text-[11px] text-fg3">
                <span>{compact(a.tokens)} tokens</span><span>{usd(a.cost_usd)}</span><span>{duration(a.latency_ms)}</span>
              </div>
              {a.issues.length > 0 && (
                <ul className="mt-2.5 space-y-1.5">
                  {a.issues.map((iss, k) => (
                    <li key={k} className="rounded-sm bg-bad/5 px-2 py-1.5 text-[12px]">
                      <div className="flex items-center gap-2"><Chip color="var(--color-bad)">{iss.code}</Chip><span className="mono text-fg2">{iss.path || "root"}</span></div>
                      <div className="mt-0.5 text-fg2">{iss.message}</div>
                    </li>
                  ))}
                </ul>
              )}
              {a.outcome === "aborted" && state.error_code === "REPEATED_OUTPUT" && (
                <p className="mt-2 flex items-center gap-1.5 text-[12px] text-run"><Equal size={13} /> identical to an earlier attempt - stopped to avoid wasted retries</p>
              )}
              {i > 0 && atts[i - 1] && <Diff runId={runId} task={task} n={a.n} prev={atts[i - 1]!} />}
            </div>
            {next && (
              <div className="ml-4 flex items-stretch gap-3 py-1">
                <div className="flex flex-col items-center"><span className="w-px flex-1 bg-line-strong" /><ArrowDown size={14} className="text-repair" /><span className="w-px flex-1 bg-line-strong" /></div>
                <div className="my-1 flex-1 rounded-sm border border-repair/40 bg-repair/5 p-2.5">
                  <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-repair"><RefreshCw size={12} />Feedback injected into attempt {next.n}</div>
                  <pre className="mono max-h-40 overflow-auto whitespace-pre-wrap text-[11.5px] text-fg2">{feedbackText[a.n] ?? (previewFromIssues(a.issues) || "(no issues recorded)")}</pre>
                  {feedbackText[a.n] === undefined && <div className="mt-1 text-[10px] text-fg3">payload-safe view (issue codes and messages). Start with --expose-payloads for the exact text.</div>}
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
