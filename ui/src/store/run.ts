import { create } from "zustand";
import { api, type ConnState } from "@/lib/api";
import { applyEvents, initialSnapshot } from "@/lib/reducer";
import type { RunEvent, Snapshot } from "@/lib/types";

interface RunState {
  runId: string | null;
  snap: Snapshot | null;
  events: RunEvent[];
  conn: ConnState;
  error: string | null;
  selected: string | null;
  follow: boolean;
  load(runId: string): Promise<void>;
  select(task: string | null): void;
  setFollow(v: boolean): void;
  close(): void;
}

let stop: (() => void) | null = null;
let buffer: RunEvent[] = [];
let raf = 0;

export const useRun = create<RunState>((set, get) => ({
  runId: null, snap: null, events: [], conn: "history", error: null, selected: null, follow: true,
  select: (selected) => set({ selected }),
  setFollow: (follow) => set({ follow }),
  close() {
    stop?.(); stop = null; buffer = []; cancelAnimationFrame(raf);
  },
  async load(runId) {
    get().close();
    set({ runId, snap: null, events: [], error: null, selected: null, conn: "history" });
    try {
      const events = await api.events(runId, 0);
      if (get().runId !== runId) return;
      const snap = applyEvents(initialSnapshot(runId), events);
      set({ snap, events });
      if (["SUCCEEDED", "FAILED", "CANCELLED", "BUDGET_EXCEEDED"].includes(snap.run.status)) return;
      const flush = () => {
        raf = 0;
        const batch = buffer; buffer = [];
        const cur = get();
        if (!batch.length || cur.runId !== runId || !cur.snap) return;
        const fresh = batch.filter((e) => e.seq > cur.snap!.seq);
        set({ snap: applyEvents(cur.snap, fresh), events: cur.events.concat(fresh) });
      };
      stop = api.stream(
        runId, snap.seq,
        (ev) => { buffer.push(ev); raf ||= requestAnimationFrame(flush); },
        (conn) => set({ conn }),
      );
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e), conn: "error" });
    }
  },
}));
