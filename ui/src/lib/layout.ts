import type { Graph } from "./types";

export const NODE_W = 232;
export const NODE_H = 104;

/** Layered layout: x by longest-path depth, y ordered by parent barycenter. Fine for hundreds of nodes. */
export function layoutGraph(g: Graph): Record<string, { x: number; y: number }> {
  const preds = new Map<string, string[]>();
  for (const n of g.nodes) preds.set(n.name, []);
  for (const e of g.edges) preds.get(e.target)?.push(e.source);
  const depth = new Map<string, number>();
  const d = (n: string): number => {
    if (depth.has(n)) return depth.get(n)!;
    depth.set(n, 0); // guard against cycles (compile() already rejects them)
    const v = Math.max(-1, ...(preds.get(n) ?? []).map(d)) + 1;
    depth.set(n, v);
    return v;
  };
  g.nodes.forEach((n) => d(n.name));
  const layers: string[][] = [];
  for (const n of g.nodes) (layers[depth.get(n.name)!] ??= []).push(n.name);
  const pos: Record<string, { x: number; y: number }> = {};
  const order = new Map<string, number>();
  layers.forEach((layer, li) => {
    if (li > 0) {
      const bary = (n: string) => {
        const p = preds.get(n) ?? [];
        return p.length ? p.reduce((a, b) => a + (order.get(b) ?? 0), 0) / p.length : 0;
      };
      layer.sort((a, b) => bary(a) - bary(b));
    }
    layer.forEach((n, i) => {
      order.set(n, i);
      pos[n] = { x: li * (NODE_W + 72), y: (i - (layer.length - 1) / 2) * (NODE_H + 40) };
    });
  });
  return pos;
}

export function topoOrder(g: Graph): string[] {
  const pos = layoutGraph(g);
  return g.nodes.map((n) => n.name).sort((a, b) => pos[a]!.x - pos[b]!.x || pos[a]!.y - pos[b]!.y);
}
