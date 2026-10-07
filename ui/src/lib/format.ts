export const usd = (n: number) => (n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`);
export const compact = (n: number) =>
  n >= 1e6 ? `${+(n / 1e6).toFixed(1)}M` : n >= 1000 ? `${+(n / 1000).toFixed(1)}k` : `${Math.round(n)}`;
export function duration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s}.${Math.floor((ms % 1000) / 100)}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}
export const clock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
export const shortId = (id: string | null | undefined) => (id ? id.slice(0, 8) : "-");
