import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { applyEvent, initialSnapshot } from "./reducer";
import type { RunEvent } from "./types";

const dir = path.resolve(import.meta.dirname, "../../../fixtures/scenarios");
const names = readdirSync(dir).filter((f) => f.endsWith(".jsonl")).map((f) => f.replace(".jsonl", ""));

// Strip fields the TS reducer legitimately does not track identically (none today) and key order.
const norm = (x: unknown) => JSON.parse(JSON.stringify(x));

describe("reducer matches Python golden snapshots", () => {
  for (const name of names) {
    it(name, () => {
      const events: RunEvent[] = readFileSync(path.join(dir, `${name}.jsonl`), "utf8")
        .trim().split("\n").map((l) => JSON.parse(l));
      let snap = initialSnapshot(events[0]!.run_id);
      for (const ev of events) snap = applyEvent(snap, ev);
      const expected = JSON.parse(readFileSync(path.join(dir, `${name}.snapshot.json`), "utf8"));
      expect(norm(snap)).toEqual(norm(expected));
    });
  }
});
