import { Check, CircleDashed, Circle, History, Loader, Minus, RotateCcw, ScanLine, X, type LucideIcon } from "lucide-react";
import type { RunStatus, TaskStatus } from "./types";

export interface StatusStyle { color: string; label: string; icon: LucideIcon; glow: boolean; pulse: "" | "pulse" | "pulse-fast" }

const S = (color: string, label: string, icon: LucideIcon, glow = false, pulse: StatusStyle["pulse"] = ""): StatusStyle =>
  ({ color, label, icon, glow, pulse });

export const TASK_STYLE: Record<TaskStatus, StatusStyle> = {
  PENDING: S("var(--color-idle)", "Pending", Circle),
  READY: S("var(--color-fg3)", "Ready", CircleDashed, true),
  RUNNING: S("var(--color-run)", "Running", Loader, true, "pulse"),
  VALIDATING: S("var(--color-repair)", "Validating", ScanLine, true, "pulse"),
  REPAIRING: S("var(--color-repair)", "Repairing", RotateCcw, true, "pulse-fast"),
  COMMITTED: S("var(--color-ok)", "Committed", Check, true),
  CACHED: S("var(--color-cache)", "Cached", History, true),
  FAILED: S("var(--color-bad)", "Failed", X, true),
  SKIPPED: S("var(--color-idle)", "Skipped", Minus),
};

export const RUN_STYLE: Record<RunStatus, { color: string; label: string; live: boolean }> = {
  CREATED: { color: "var(--color-idle)", label: "Created", live: false },
  RUNNING: { color: "var(--color-run)", label: "Running", live: true },
  SUCCEEDED: { color: "var(--color-ok)", label: "Succeeded", live: false },
  FAILED: { color: "var(--color-bad)", label: "Failed", live: false },
  CANCELLED: { color: "var(--color-idle)", label: "Cancelled", live: false },
  BUDGET_EXCEEDED: { color: "var(--color-bad)", label: "Budget exceeded", live: false },
  AWAITING_HUMAN: { color: "var(--color-repair)", label: "Awaiting human", live: true },
};

export const ACTIVE: TaskStatus[] = ["RUNNING", "VALIDATING", "REPAIRING"];
export const OK: TaskStatus[] = ["COMMITTED", "CACHED"];
export const isTerminalRun = (s: RunStatus) => ["SUCCEEDED", "FAILED", "CANCELLED", "BUDGET_EXCEEDED"].includes(s);
