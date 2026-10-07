import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { ComparePage } from "@/features/compare/ComparePage";
import { ConsolePage } from "@/features/console/ConsolePage";
import { RunsPage } from "@/features/runs/RunsPage";
import { CommandPalette } from "@/features/shell/CommandPalette";
import { Label } from "@/components/ui";
import { api, type Health } from "@/lib/api";

function Settings() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => { api.health().then(setH).catch(() => setH(null)); }, []);
  return (
    <div className="mx-auto max-w-xl px-8 py-8">
      <Label>Console</Label><h1 className="mb-6 text-2xl font-semibold">Settings</h1>
      <dl className="space-y-2 text-sm">
        <div className="flex justify-between border-b border-line py-2"><dt className="text-fg3">Version</dt><dd className="mono">{h?.version ?? "-"}</dd></div>
        <div className="flex justify-between border-b border-line py-2"><dt className="text-fg3">Address</dt><dd className="mono">{location.host} (loopback only)</dd></div>
        <div className="flex justify-between border-b border-line py-2"><dt className="text-fg3">Artifact payloads</dt><dd className={h?.payloads_exposed ? "text-run" : "text-ok"}>{h?.payloads_exposed ? "exposed" : "hidden (hashes and issue codes only)"}</dd></div>
      </dl>
    </div>
  );
}

export function App() {
  return (
    <div className="h-full">
      <Routes>
        <Route path="/" element={<RunsPage />} />
        <Route path="/runs/:runId/*" element={<ConsolePage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<RunsPage />} />
      </Routes>
      <CommandPalette />
    </div>
  );
}
