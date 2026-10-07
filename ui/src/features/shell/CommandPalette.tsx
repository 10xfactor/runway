import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Kbd } from "@/components/ui";
import { api } from "@/lib/api";
import type { RunSummary } from "@/lib/types";
import { useRun } from "@/store/run";

const SHORTCUTS: [string, string][] = [["Cmd/Ctrl K", "Command palette"], ["j / k", "Next / previous task"], ["r", "Replay from selected task"], ["Esc", "Close inspector"], ["?", "This help"]];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const nav = useNavigate();
  const loc = useLocation();
  const { snap, runId, selected, follow, setFollow } = useRun();
  const inRun = loc.pathname.startsWith("/runs/") && snap;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      else if (e.key === "?" && !(e.target as HTMLElement).closest("input,textarea")) setHelp((h) => !h);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { if (open) api.runs().then(setRuns).catch(() => setRuns([])); }, [open]);
  const go = (to: string) => { setOpen(false); nav(to); };

  return (
    <>
      <Command.Dialog open={open} onOpenChange={setOpen} label="Command palette" overlayClassName="fixed inset-0 z-[59] bg-black/50" contentClassName="fixed left-1/2 top-[18%] z-[60] w-[560px] -translate-x-1/2 overflow-hidden rounded-md border border-line-strong bg-panel shadow-2xl">
        <Command.Input placeholder="Jump to a run, task, or action..." className="w-full border-b border-line bg-transparent px-4 py-3 text-sm outline-none placeholder:text-fg3" />
        <Command.List className="max-h-80 overflow-auto p-2">
          <Command.Empty className="p-4 text-center text-fg3">No results</Command.Empty>
          <Command.Group heading="Navigate" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-fg3">
            <Item onSelect={() => go("/")}>Runs</Item>
            <Item onSelect={() => go("/settings")}>Settings</Item>
          </Command.Group>
          {inRun && (
            <Command.Group heading="This run" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-fg3">
              {Object.keys(snap.tasks).map((t) => <Item key={t} onSelect={() => go(`/runs/${runId}/tasks/${t}`)}>Inspect task: {t}</Item>)}
              <Item onSelect={() => go(`/runs/${runId}/replay${selected ? `?from=${selected}` : ""}`)}>Replay{selected ? ` from ${selected}` : ""}...</Item>
              <Item onSelect={() => { setFollow(!follow); setOpen(false); }}>Toggle follow active</Item>
              <Item onSelect={() => { void navigator.clipboard?.writeText(runId ?? ""); setOpen(false); }}>Copy run id</Item>
            </Command.Group>
          )}
          <Command.Group heading="Runs" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-fg3">
            {runs.slice(0, 15).map((r) => <Item key={r.run_id} onSelect={() => go(`/runs/${r.run_id}`)}><span className="mono">{r.run_id}</span> <span className="text-fg3">{r.graph_id} - {r.status}</span></Item>)}
          </Command.Group>
        </Command.List>
      </Command.Dialog>
      {help && (
        <div role="dialog" aria-label="Keyboard shortcuts" className="fixed bottom-6 right-6 z-[60] rounded-md border border-line-strong bg-panel p-4 shadow-2xl" onClick={() => setHelp(false)}>
          <div className="label mb-2">Shortcuts</div>
          <ul className="space-y-1.5">{SHORTCUTS.map(([k, d]) => <li key={k} className="flex items-center justify-between gap-6 text-xs"><span className="text-fg2">{d}</span><Kbd>{k}</Kbd></li>)}</ul>
        </div>
      )}
    </>
  );
}

const Item = (p: { onSelect: () => void; children: React.ReactNode }) => (
  <Command.Item onSelect={p.onSelect} className="flex cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-[13px] data-[selected=true]:bg-raised">{p.children}</Command.Item>
);
