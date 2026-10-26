import { useEffect, useState } from "react";
import { compareReplay, type Slot, uploadCompare } from "../api/client";
import type { SessionInfo } from "../api/types";
import { describeDifferences, type RunSummary, summarize } from "../models/compare";
import { Lanes } from "./Lanes";

interface Props {
  session: SessionInfo;
  onHome: () => void;
  onToggleTheme: () => void;
}

type Runs = Record<Slot, RunSummary | null>;
const SLOTS: Slot[] = ["a", "b"];

const seconds = (ns: number) => `${(ns / 1e9).toFixed(2)}s`;
const yesNo = (v: boolean | null) => (v === null ? "unknown" : v ? "yes" : "no");

/** Rows of the facts table: label and how to read it from a summary. */
const ROWS: [string, (r: RunSummary) => string][] = [
  ["Program", (r) => r.script ?? "–"],
  ["Python", (r) => `${r.implementation} ${r.python}`],
  ["Free-threaded build", (r) => yesNo(r.freeThreaded)],
  ["GIL enabled at runtime", (r) => yesNo(r.gilEnabled)],
  ["Platform", (r) => r.platform || "–"],
  ["Wall time", (r) => seconds(r.durationNs)],
  ["Events", (r) => String(r.events)],
  ["Work spans open at once (max)", (r) => String(r.maxOverlap)],
];

/**
 * Two recordings side by side, on one time scale. Only recorded facts are
 * compared; nothing here measures CPU use or who held the GIL.
 */
export function Compare({ session, onHome, onToggleTheme }: Props) {
  const [runs, setRuns] = useState<Runs>({ a: null, b: null });
  const [error, setError] = useState<string | null>(null);

  const load = async (slot: Slot, label: string) => {
    const summary = summarize(await compareReplay(slot), label);
    setRuns((old) => ({ ...old, [slot]: summary }));
  };
  useEffect(() => {
    for (const slot of SLOTS) {
      const label = session.compare[slot];
      if (label) load(slot, label).catch((e) => setError(String(e)));
    }
  }, [session]);

  const pick = async (slot: Slot, file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      await uploadCompare(slot, file, file.name);
      await load(slot, file.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const [a, b] = [runs.a, runs.b];
  return (
    <div className="home compare" data-testid="compare-screen">
      <header className="top">
        <div className="brand"><b>Concurim</b><span>Compare two recordings</span></div>
        <div className="meta">
          <button className="link" onClick={onHome}>← Home</button>
          <button className="link" onClick={onToggleTheme} aria-label="Toggle theme">◐</button>
        </div>
      </header>
      <main>
        <p className="muted">
          Record the same program twice (for example under a GIL build and a
          free-threaded build) and load both here. Traces keep the Python
          version and whether the GIL was enabled.
        </p>
        {error && <p className="warning" data-testid="compare-error">{error}</p>}
        <div className="slots">
          {SLOTS.map((slot) => (
            <label key={slot} className="slot">
              Recording {slot.toUpperCase()}: {runs[slot]?.label ?? "none yet"}
              <input type="file" accept=".concurim" data-testid={`compare-${slot}`}
                onChange={(e) => pick(slot, e.target.files?.[0])} />
            </label>
          ))}
        </div>
        {a && b && (
          <>
            <table data-testid="compare-table">
              <thead><tr><th /><th>{a.label}</th><th>{b.label}</th></tr></thead>
              <tbody>
                {ROWS.map(([name, read]) => (
                  <tr key={name}><th>{name}</th><td>{read(a)}</td><td>{read(b)}</td></tr>
                ))}
              </tbody>
            </table>
            <ul data-testid="compare-notes">
              {describeDifferences(a, b).map((t) => <li key={t}>{t}</li>)}
            </ul>
            <Lanes runs={[a, b]} />
            <p className="muted small">
              Bars are work the program marked or a pool ran. Both rows use one
              time scale. Overlap of bars is not CPU parallelism, and Concurim
              cannot see GIL ownership. Timings include recording overhead.
            </p>
          </>
        )}
      </main>
    </div>
  );
}
