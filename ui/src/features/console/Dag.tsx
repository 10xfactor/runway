import { Background, BackgroundVariant, Controls, MiniMap, ReactFlow, useReactFlow, ReactFlowProvider, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef } from "react";
import { layoutGraph } from "@/lib/layout";
import { ACTIVE, OK, TASK_STYLE } from "@/lib/status";
import type { Graph, TaskState } from "@/lib/types";
import { LightEdge } from "./LightEdge";
import { TaskNode, type TaskFlowNode } from "./TaskNode";

const nodeTypes = { task: TaskNode };
const edgeTypes = { light: LightEdge };

export interface DagProps {
  graph: Graph;
  tasks: Record<string, TaskState>;
  selected: string | null;
  onSelect: (name: string | null) => void;
  follow?: boolean;
  overlay?: Record<string, { kind: "reuse" | "rerun" | "stale"; note?: string }>;
  minimap?: boolean;
}

function DagInner({ graph, tasks, selected, onSelect, follow, overlay, minimap = true }: DagProps) {
  const pos = useMemo(() => layoutGraph(graph), [graph]);
  const rf = useReactFlow();
  const nodes: TaskFlowNode[] = useMemo(
    () => graph.nodes.map((n) => ({
      id: n.name, type: "task" as const, position: pos[n.name]!, draggable: false,
      data: { node: n, state: tasks[n.name]!, selected: selected === n.name, overlay: overlay?.[n.name]?.kind, overlayNote: overlay?.[n.name]?.note },
    })),
    [graph, tasks, selected, pos, overlay],
  );
  const edges: Edge[] = useMemo(
    () => graph.edges.map((e) => {
      const s = tasks[e.source]?.status, t = tasks[e.target]?.status;
      const mode = t && ACTIVE.includes(t) ? "active" : s && t && OK.includes(s) && OK.includes(t) ? "done" : "idle";
      return { id: `${e.source}-${e.target}`, source: e.source, target: e.target, type: "light", data: { mode } };
    }),
    [graph, tasks],
  );
  const fitted = useRef(false);
  useEffect(() => {
    if (!fitted.current && nodes.length) { fitted.current = true; for (const ms of [30, 400]) setTimeout(() => rf.fitView({ padding: 0.2, duration: 300 }), ms); } // 2nd pass: dialogs animate in
  }, [nodes.length, rf]);
  const activeKey = Object.entries(tasks).filter(([, t]) => ACTIVE.includes(t.status)).map(([n]) => n).join(",");
  useEffect(() => {
    if (!follow) return;
    if (!activeKey) { if (fitted.current) rf.fitView({ padding: 0.2, duration: 400 }); return; }
    rf.fitView({ nodes: activeKey.split(",").map((id) => ({ id })), padding: 0.8, duration: 400, maxZoom: 1.1 });
  }, [follow, activeKey, rf]);

  return (
    <ReactFlow
      nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.2} maxZoom={1.6}
      nodesConnectable={false} proOptions={{ hideAttribution: true }}
      onNodeClick={(_, n) => onSelect(n.id)} onPaneClick={() => onSelect(null)}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1b232c" />
      <Controls showInteractive={false} />
      {minimap && <MiniMap pannable zoomable nodeColor={(n) => TASK_STYLE[(n.data as { state: TaskState }).state.status].color} maskColor="rgba(10,13,16,.7)" />}
    </ReactFlow>
  );
}

export function Dag(props: DagProps) {
  return <ReactFlowProvider><DagInner {...props} /></ReactFlowProvider>;
}
