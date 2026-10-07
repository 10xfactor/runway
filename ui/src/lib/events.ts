import { compact, usd } from "./format";
import type { Issue, RunEvent } from "./types";

export const EVENT_GROUP: Record<string, "run" | "task" | "model" | "validation" | "budget"> = {
  "run.": "run", "task.": "task", "attempt.": "task", "model.": "model", "artifact.": "model",
  "validation.": "validation", "agent.": "validation", "budget.": "budget",
};
export const groupOf = (type: string) => EVENT_GROUP[Object.keys(EVENT_GROUP).find((p) => type.startsWith(p)) ?? ""] ?? "run";

export const GROUP_COLOR = {
  run: "var(--color-fg2)", task: "var(--color-ok)", model: "var(--color-run)",
  validation: "var(--color-repair)", budget: "var(--color-bad)",
} as const;

/** One-line, payload-free summary of an event. */
export function summarizeEvent(e: RunEvent): string {
  const d = e.data;
  switch (e.type) {
    case "model.generated": return `${compact(d.prompt_tokens + d.completion_tokens)} tokens - ${usd(d.cost_usd)}`;
    case "model.requested": return `${d.model}${d.feedback_issue_count ? ` - with feedback from ${d.feedback_issue_count} prior attempt(s)` : ""}`;
    case "validation.started": return `stage ${d.stage}: ${(d.validators as string[]).join(", ")}`;
    case "validation.failed": return (d.results as { issues: Issue[] }[]).flatMap((r) => r.issues).map((i) => `${i.code}@${i.path || "root"}`).join(", ");
    case "validation.passed": return `${d.stages_run} stage(s) accepted`;
    case "agent.retry": return `repair attempt ${d.next_attempt} (feedback ~${d.feedback_tokens} tokens)`;
    case "task.failed": case "run.failed": return String(d.error_code);
    case "task.cached": return `reused from ${d.from_run_id}`;
    case "task.committed": return `${d.attempts} attempt(s) - ${usd(d.cost_usd)}`;
    case "task.skipped": return `blocked by ${d.caused_by_task}`;
    case "budget.warning": case "budget.exceeded": return `${d.scope} ${d.dimension} ${Math.round(d.used * 100) / 100}/${d.limit}`;
    case "run.created": return `graph ${d.graph_id}`;
    default: return "";
  }
}

/** Same rendering as runway.core.validation.render_feedback, from the (redacted) issues only. */
export function previewFromIssues(issues: Issue[]): string {
  return issues.map((i) => `- [${i.code}]${i.path ? ` at \`${i.path}\`` : ""}: ${i.message}${i.hint ? ` Hint: ${i.hint}` : ""}`).join("\n");
}
