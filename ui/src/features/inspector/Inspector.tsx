import * as Tabs from "@radix-ui/react-tabs";
import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Chip, Label, TaskBadge } from "@/components/ui";
import { api, type TaskDetail } from "@/lib/api";
import { groupOf, summarizeEvent, GROUP_COLOR } from "@/lib/events";
import { compact, duration, shortId, usd } from "@/lib/format";
import type { GraphNode, RunEvent, TaskState } from "@/lib/types";
import { RepairLens } from "./RepairLens";

const TABS = ["overview", "repair", "validation", "events", "cost"] as const;
const TAB_LABEL = { overview: "Overview", repair: "Repair Lens", validation: "Validation", events: "Events", cost: "Cost" };

function KV({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="flex items-baseline justify-between gap-4 border-b border-line/60 py-1.5"><dt className="text-fg3">{k}</dt><dd className="mono truncate text-right text-fg">{children}</dd></div>;
}

export function Inspector({ runId, task, node, state, events, onClose }: {
  runId: string; task: string; node: GraphNode | undefined; state: TaskState; events: RunEvent[]; onClose: () => void;
}) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("overview");
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const settled = `${state.status}:${state.attempts.length}`;
  useEffect(() => {
    let live = true;
    api.task(runId, task).then((d) => live && setDetail(d)).catch(() => live && setDetail(null));
    return () => { live = false; };
  }, [runId, task, settled]);
  const feedbackText = useMemo(() => Object.fromEntries((detail?.state.attempts ?? []).filter((a) => a.feedback_text).map((a) => [a.n, a.feedback_text!])), [detail]);
  const mine = useMemo(() => events.filter((e) => e.task_name === task), [events, task]);
  const rejected = state.attempts.filter((a) => a.outcome === "rejected").length;

  return (
    <aside className="flex h-full w-[420px] shrink-0 flex-col border-l border-line bg-panel" aria-label={`Inspector for ${task}`}>
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <Label>Inspector</Label>
          <div className="mt-0.5 flex items-center gap-3"><h2 className="text-base font-semibold">{task}</h2><TaskBadge status={state.status} /></div>
        </div>
        <button aria-label="Close inspector" onClick={onClose} className="rounded p-1 text-fg3 hover:bg-raised hover:text-fg"><X size={16} /></button>
      </header>
      <Tabs.Root value={tab} onValueChange={(v) => setTab(v as (typeof TABS)[number])} className="flex min-h-0 flex-1 flex-col">
        <Tabs.List className="flex gap-0.5 border-b border-line px-2" aria-label="Inspector sections">
          {TABS.map((t) => (
            <Tabs.Trigger key={t} value={t} className="relative px-3 py-2.5 text-xs font-medium text-fg3 outline-none transition-colors hover:text-fg2 data-[state=active]:text-fg data-[state=active]:after:absolute data-[state=active]:after:inset-x-2 data-[state=active]:after:bottom-0 data-[state=active]:after:h-0.5 data-[state=active]:after:bg-run">
              {TAB_LABEL[t]}{t === "repair" && rejected > 0 && <span className="ml-1.5 rounded-full bg-bad/20 px-1.5 text-[10px] text-bad">{rejected}</span>}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          <Tabs.Content value="overview">
            <dl>
              <KV k="Model">{node?.model}</KV>
              <KV k="Input contract">{node?.input_contract}</KV>
              <KV k="Output contract">{node?.output_contract}</KV>
              <KV k="Attempts">{state.attempts.length} / {(node?.max_retries ?? 0) + 1}</KV>
              <KV k="Cache key">{shortId(state.cache_key)}</KV>
              <KV k="Output artifact">{shortId(state.artifact_id)}</KV>
              {state.from_run_id && <KV k="Reused from">{state.from_run_id}</KV>}
              {state.error_code && <KV k="Error"><span className="text-bad">{state.error_code}</span></KV>}
            </dl>
            <Label className="mt-5">Cache key components</Label>
            <dl className="mt-1">{Object.entries(state.cache_components).map(([k, v]) => <KV key={k} k={k}>{shortId(v)}</KV>)}</dl>
          </Tabs.Content>
          <Tabs.Content value="repair"><RepairLens runId={runId} task={task} state={detail?.state ?? state} feedbackText={feedbackText} /></Tabs.Content>
          <Tabs.Content value="validation">
            <Label>Validator chain</Label>
            <ol className="mt-2 space-y-2">
              {(node?.validators.length ? node.validators : [["schema"]]).map((stage, i) => (
                <li key={i} className="rounded-sm border border-line bg-tarmac p-2.5">
                  <div className="mb-1 text-[11px] text-fg3">Stage {i + 1}{stage.length > 1 ? " (concurrent)" : ""}</div>
                  <div className="flex flex-wrap gap-1.5">{stage.map((v) => <Chip key={v}>{v}</Chip>)}</div>
                </li>
              ))}
            </ol>
            <Label className="mt-5">Issues by attempt</Label>
            {state.attempts.every((a) => !a.issues.length) ? <p className="mt-2 text-fg3">No issues recorded.</p> : state.attempts.map((a) => a.issues.length > 0 && (
              <div key={a.n} className="mt-2"><div className="mb-1 text-[11px] text-fg3">Attempt {a.n}</div>
                {a.issues.map((i, k) => <div key={k} className="mono mb-1 rounded-sm bg-bad/5 px-2 py-1 text-[12px]"><span className="text-bad">{i.code}</span> <span className="text-fg2">{i.path || "root"}</span><div className="text-fg3">{i.message}</div></div>)}
              </div>
            ))}
          </Tabs.Content>
          <Tabs.Content value="events">
            <ul className="mono space-y-1 text-[12px]">
              {mine.map((e) => (
                <li key={e.seq} className="flex gap-2"><span className="w-8 text-right text-fg3">{e.seq}</span><span style={{ color: GROUP_COLOR[groupOf(e.type)] }}>{e.type}</span><span className="truncate text-fg3">{summarizeEvent(e)}</span></li>
              ))}
            </ul>
          </Tabs.Content>
          <Tabs.Content value="cost">
            <dl>
              <KV k="Total tokens">{compact(state.tokens)}</KV><KV k="Total cost">{usd(state.cost_usd)}</KV><KV k="Duration">{duration(state.duration_ms)}</KV>
            </dl>
            <Label className="mt-5">Per attempt</Label>
            <div className="mt-2 space-y-1.5">
              {state.attempts.map((a) => {
                const max = Math.max(...state.attempts.map((x) => x.tokens), 1);
                return (
                  <div key={a.n} className="flex items-center gap-2 text-[12px]">
                    <span className="w-6 text-fg3">#{a.n}</span>
                    <div className="h-2 flex-1 rounded-full bg-line"><div className="h-2 rounded-full" style={{ width: `${(a.tokens / max) * 100}%`, background: a.outcome === "accepted" ? "var(--color-ok)" : "var(--color-bad)" }} /></div>
                    <span className="mono w-28 text-right text-fg2">{compact(a.tokens)} - {usd(a.cost_usd)}</span>
                  </div>
                );
              })}
            </div>
          </Tabs.Content>
        </div>
      </Tabs.Root>
    </aside>
  );
}
