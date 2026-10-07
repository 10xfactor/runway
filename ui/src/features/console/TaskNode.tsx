import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import clsx from "clsx";
import { memo } from "react";
import { Beacon, Chip, TaskBadge } from "@/components/ui";
import { duration, usd } from "@/lib/format";
import { NODE_H, NODE_W } from "@/lib/layout";
import { TASK_STYLE } from "@/lib/status";
import type { GraphNode, TaskState } from "@/lib/types";

export type TaskNodeData = {
  node: GraphNode; state: TaskState; selected: boolean; overlay?: "reuse" | "rerun" | "stale"; overlayNote?: string;
} & Record<string, unknown>;
export type TaskFlowNode = Node<TaskNodeData, "task">;

function liveLine(n: GraphNode, t: TaskState): string {
  const done = t.attempts.length;
  switch (t.status) {
    case "RUNNING": return t.attempts.length ? `calling model - attempt ${done}` : "starting";
    case "VALIDATING": return `validating: ${n.validators.flat().join(", ") || "schema"}`;
    case "REPAIRING": return `repair ${done}/${n.max_retries + 1}`;
    case "CACHED": return `from ${t.from_run_id ?? "parent"}`;
    case "FAILED": return t.error_code ?? "failed";
    case "SKIPPED": return "upstream failed";
    case "COMMITTED": return `${done} attempt${done === 1 ? "" : "s"} - ${duration(t.duration_ms)}`;
    default: return "waiting";
  }
}

const OVERLAY = {
  reuse: { color: "var(--color-cache)", label: "reuse" },
  rerun: { color: "var(--color-run)", label: "re-run" },
  stale: { color: "var(--color-bad)", label: "stale" },
};

function TaskNodeImpl({ data }: NodeProps<TaskFlowNode>) {
  const { node, state, selected, overlay, overlayNote } = data;
  const st = TASK_STYLE[state.status];
  const ov = overlay ? OVERLAY[overlay] : null;
  const accent = ov?.color ?? st.color;
  const active = state.status === "VALIDATING" || state.status === "REPAIRING";
  return (
    <div
      role="button"
      aria-label={`${node.name}: ${st.label}`}
      className={clsx(
        "relative overflow-hidden rounded-md border bg-panel transition-[box-shadow,border-color] duration-200",
        state.status === "SKIPPED" && "hatch opacity-70",
        state.status === "COMMITTED" && "settle",
        ov?.label === "stale" && "border-dashed",
      )}
      style={{
        width: NODE_W, height: NODE_H,
        borderColor: selected ? "var(--color-fg)" : `color-mix(in srgb, ${accent} ${state.status === "PENDING" ? 35 : 70}%, var(--color-line))`,
        boxShadow: st.glow || ov ? `0 0 0 1px color-mix(in srgb, ${accent} 18%, transparent), 0 0 22px -4px color-mix(in srgb, ${accent} 38%, transparent)` : undefined,
      }}
    >
      {active && <span className="scanline" />}
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-line-strong !bg-raised" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-line-strong !bg-raised" />
      <div className="flex h-full flex-col justify-between p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <Beacon color={accent} glow={st.glow} pulse={st.pulse} />
            <span className="truncate text-[13px] font-semibold">{node.name}</span>
          </div>
          {ov ? <span className="label" style={{ color: accent }}>{ov.label}</span> : <TaskBadge status={state.status} compact />}
        </div>
        <div className="flex items-center gap-1.5">
          <Chip title="model">{node.model}</Chip>
          <Chip title="output contract">{node.output_contract}</Chip>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1" aria-label="attempts">
            {state.attempts.map((a) => (
              <span key={a.n} title={`attempt ${a.n}: ${a.outcome}`} className="h-1.5 w-3 rounded-[2px]"
                style={{ background: a.outcome === "accepted" ? "var(--color-ok)" : a.outcome === "rejected" || a.outcome === "error" ? "var(--color-bad)" : a.outcome === "aborted" ? "var(--color-idle)" : "var(--color-run)" }} />
            ))}
          </div>
          <span className="mono text-[11px] text-fg3">{state.cost_usd ? usd(state.cost_usd) : ""}</span>
        </div>
        <div className="truncate text-[11px] text-fg3">{overlayNote ?? liveLine(node, state)}</div>
      </div>
    </div>
  );
}
export const TaskNode = memo(TaskNodeImpl);
