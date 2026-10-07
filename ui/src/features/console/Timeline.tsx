import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Beacon, Label } from "@/components/ui";
import { GROUP_COLOR, groupOf, summarizeEvent } from "@/lib/events";
import type { RunEvent } from "@/lib/types";

const FILTERS = ["all", "task", "model", "validation", "budget"] as const;

export function Timeline({ events, selected, onSelect, startTs }: {
  events: RunEvent[]; selected: string | null; onSelect: (t: string) => void; startTs: string | null;
}) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [follow, setFollow] = useState(true);
  const [open, setOpen] = useState(true);
  const [height, setHeight] = useState(230);
  const rows = useMemo(() => events.filter((e) => filter === "all" || groupOf(e.type) === filter), [events, filter]);
  const ref = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: rows.length, getScrollElement: () => ref.current, estimateSize: () => 26, overscan: 12 });
  useEffect(() => { if (follow && rows.length) v.scrollToIndex(rows.length - 1); }, [rows.length, follow, v]);
  const t0 = startTs ? Date.parse(startTs) : events[0] ? Date.parse(events[0].ts) : 0;

  const drag = (e: React.PointerEvent) => {
    const startY = e.clientY, startH = height;
    const move = (m: PointerEvent) => setHeight(Math.min(520, Math.max(120, startH + startY - m.clientY)));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  return (
    <section className="border-t border-line bg-panel" style={{ height: open ? height : 40 }} aria-label="Event timeline">
      <div onPointerDown={open ? drag : undefined} className={clsx("h-1 w-full", open && "cursor-row-resize hover:bg-line-strong")} />
      <div className="flex h-9 items-center gap-3 px-4">
        <Label>Timeline</Label>
        <span className="mono text-[11px] text-fg3">{events.length} events</span>
        <div className="ml-2 flex gap-1">
          {FILTERS.map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={clsx("rounded-full border px-2.5 py-0.5 text-[11px] capitalize transition-colors", filter === f ? "border-fg3 bg-raised text-fg" : "border-line text-fg3 hover:text-fg2")}>
              {f}
            </button>
          ))}
        </div>
        <label className="ml-auto flex items-center gap-1.5 text-[11px] text-fg3">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow
        </label>
        <button aria-label={open ? "Collapse timeline" : "Expand timeline"} onClick={() => setOpen(!open)} className="text-fg3 hover:text-fg">
          {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </div>
      {open && (
        <div ref={ref} className="overflow-auto" style={{ height: height - 40 - 4 }}>
          <div style={{ height: v.getTotalSize(), position: "relative" }}>
            {v.getVirtualItems().map((vi) => {
              const e = rows[vi.index]!;
              const color = GROUP_COLOR[groupOf(e.type)];
              const rel = Math.max(0, Date.parse(e.ts) - t0);
              return (
                <button key={e.seq} onClick={() => e.task_name && onSelect(e.task_name)}
                  className={clsx("mono absolute left-0 flex w-full items-center gap-3 px-4 text-left text-[12px] hover:bg-raised", selected && e.task_name === selected && "bg-raised")}
                  style={{ top: vi.start, height: vi.size }}>
                  <span className="w-10 text-right text-fg3">{e.seq}</span>
                  <span className="w-14 text-fg3">+{(rel / 1000).toFixed(1)}s</span>
                  <Beacon color={color} />
                  <span className="w-44 shrink-0" style={{ color }}>{e.type}</span>
                  <span className="w-36 shrink-0 truncate text-fg2">{e.task_name ?? ""}{e.attempt_no ? `#${e.attempt_no}` : ""}</span>
                  <span className="truncate text-fg3">{summarizeEvent(e)}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
