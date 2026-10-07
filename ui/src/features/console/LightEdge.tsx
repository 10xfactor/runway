import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

/** Approach-light edge: dashes travel downstream while the target is working; solid dim green once committed. */
export function LightEdge(p: EdgeProps) {
  const [path] = getBezierPath(p);
  const mode = (p.data as { mode?: "idle" | "active" | "done" } | undefined)?.mode ?? "idle";
  const stroke = mode === "active" ? "var(--color-run)" : mode === "done" ? "color-mix(in srgb, var(--color-ok) 55%, var(--color-line))" : "var(--color-line-strong)";
  return <BaseEdge path={path} className={mode === "active" ? "edge-active" : undefined} style={{ stroke, strokeWidth: mode === "active" ? 2 : 1.5, strokeDasharray: mode === "idle" ? "3 5" : undefined }} />;
}
