import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { RUN_STYLE, TASK_STYLE } from "@/lib/status";
import type { RunStatus, TaskStatus } from "@/lib/types";

export function Beacon({ color, glow, pulse = "" }: { color: string; glow?: boolean; pulse?: string }) {
  return <span className={clsx("beacon", glow && "glow", pulse)} style={{ "--c": color } as React.CSSProperties} aria-hidden />;
}

export function TaskBadge({ status, compact }: { status: TaskStatus; compact?: boolean }) {
  const s = TASK_STYLE[status];
  const Icon = s.icon;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium" style={{ color: s.color }}>
      <Icon size={13} className={status === "RUNNING" ? "animate-[spin_1.6s_linear_infinite]" : ""} aria-hidden />
      {!compact && s.label}
    </span>
  );
}

export function RunPill({ status }: { status: RunStatus }) {
  const s = RUN_STYLE[status];
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line bg-panel px-2.5 py-1 text-xs font-semibold" style={{ color: s.color }}>
      <Beacon color={s.color} glow pulse={s.live ? "pulse" : ""} />
      {s.label.toUpperCase()}
    </span>
  );
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("label", className)}>{children}</div>;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="mono rounded border border-line-strong bg-raised px-1.5 py-0.5 text-[10px] text-fg2">{children}</kbd>;
}

export function Chip({ children, color, title }: { children: ReactNode; color?: string; title?: string }) {
  return (
    <span title={title} className="mono inline-flex items-center rounded-sm border border-line bg-raised px-1.5 py-0.5 text-[11px] text-fg2" style={color ? { color, borderColor: `color-mix(in srgb, ${color} 40%, transparent)` } : undefined}>
      {children}
    </span>
  );
}

/** Runway-lights meter: a row of ticks that light up with usage; amber at 80%, red at 100%. */
export function Meter({ used, limit, ticks = 24 }: { used: number; limit: number | null; ticks?: number }) {
  const ratio = limit ? Math.min(used / limit, 1) : 0;
  const lit = Math.round(ratio * ticks);
  const color = ratio >= 1 ? "var(--color-bad)" : ratio >= 0.8 ? "var(--color-run)" : "var(--color-ok)";
  return (
    <div className="flex gap-[3px]" role="meter" aria-valuenow={used} aria-valuemax={limit ?? undefined}>
      {Array.from({ length: ticks }, (_, i) => (
        <span key={i} className="h-3 w-[5px] rounded-[1px] transition-colors duration-200" style={{ background: i < lit ? color : "var(--color-line)", boxShadow: i < lit ? `0 0 6px color-mix(in srgb, ${color} 45%, transparent)` : undefined }} />
      ))}
    </div>
  );
}

/** Digits roll (not fade) when the value changes; tabular numerals prevent layout shift. */
export function DigitRoll({ value, className }: { value: string; className?: string }) {
  return (
    <span className={clsx("mono inline-flex overflow-hidden", className)} aria-label={value}>
      <AnimatePresence mode="popLayout" initial={false}>
        {value.split("").map((ch, i) => (
          <motion.span key={`${i}-${ch}`} initial={{ y: "70%", opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: "-70%", opacity: 0 }} transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}>
            {ch}
          </motion.span>
        ))}
      </AnimatePresence>
    </span>
  );
}

export function Button({ children, variant = "default", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "danger" | "ghost" }) {
  return (
    <button
      {...p}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-sm border px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        variant === "primary" && "border-run bg-run text-tarmac hover:brightness-110",
        variant === "default" && "border-line-strong bg-raised text-fg hover:bg-line",
        variant === "danger" && "border-bad/50 bg-bad/10 text-bad hover:bg-bad/20",
        variant === "ghost" && "border-transparent text-fg2 hover:bg-raised",
        p.className,
      )}
    >
      {children}
    </button>
  );
}

export function Sparkline({ values, color = "var(--color-run)", w = 90, h = 22 }: { values: number[]; color?: string; w?: number; h?: number }) {
  if (values.length < 2) return <span className="text-fg3">-</span>;
  const max = Math.max(...values, 1e-9);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - (v / max) * (h - 4)}`).join(" ");
  return (
    <svg width={w} height={h} aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function RunwayArt() {
  return (
    <svg width="220" height="120" viewBox="0 0 220 120" aria-hidden className="opacity-90">
      <path d="M70 118 L102 6 H118 L150 118 Z" fill="var(--color-panel)" stroke="var(--color-line-strong)" />
      {[14, 34, 58, 86].map((y, i) => (
        <rect key={y} x={108 - i * 0.2} y={y} width={4 + i * 0.4} height={10 + i * 3} rx="1" fill="var(--color-run)" opacity={0.95 - i * 0.12} />
      ))}
      {[0, 1, 2, 3, 4].map((i) => (<circle key={i} cx={95 - i * 4.5} cy={30 + i * 20} r="1.6" fill="var(--color-ok)" opacity=".7" />))}
      {[0, 1, 2, 3, 4].map((i) => (<circle key={i} cx={125 + i * 4.5} cy={30 + i * 20} r="1.6" fill="var(--color-ok)" opacity=".7" />))}
    </svg>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 py-16 text-center">
      <RunwayArt />
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-fg2">{children}</p>
      {action}
    </div>
  );
}
