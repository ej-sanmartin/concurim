import { useState } from "react";
import { sampleSource } from "../api/client";
import type { Observability, SampleInfo, SessionInfo } from "../api/types";

const LEVEL: Record<Observability, { name: string; hint: string }> = {
  managed: {
    name: "Concurim-managed",
    hint: "Uses TracedQueue and TracedThread: full detail, including item identity.",
  },
  queues: {
    name: "Automatic: threads + queues",
    hint: "No Concurim imports; queue.Queue is observed while recording.",
  },
  sync: {
    name: "Automatic: + locks, semaphores, executors",
    hint: "No Concurim imports; locks, semaphores and thread pools created by the program are observed.",
  },
  asyncio: {
    name: "Automatic: + asyncio",
    hint: "No Concurim imports; asyncio tasks, queues and locks are observed too.",
  },
  threads: {
    name: "Automatic: threads only",
    hint: "No Concurim imports; only thread lifetimes are observed.",
  },
};

/** Display order. Anything not listed is appended to the last group. */
const GROUPS: { id: string; title: string; ids: string[] }[] = [
  {
    id: "queues",
    title: "Queues",
    ids: [
      "producer-consumer", "backpressure", "lineage-pipeline", "shutdown",
      "plain-threads", "plain-queues",
    ],
  },
  {
    id: "locks",
    title: "Locks and events",
    ids: [
      "lock-contention", "lock-order", "semaphore", "event-gate",
      "barrier", "condition-mailbox",
    ],
  },
  {
    id: "pools",
    title: "Pools and processes",
    ids: [
      "thread-pool", "cpu-threads", "future-control", "process-pool",
      "process-pool-map", "process-share",
    ],
  },
  {
    id: "asyncio",
    title: "Asyncio",
    ids: ["asyncio-tasks", "task-group", "asyncio-queue", "asyncio-condition"],
  },
];

interface Props {
  session: SessionInfo;
  onOpen: (sample: SampleInfo) => void;
  busy: boolean;
}

/** One bundled recording: a row, with its notes and source on demand. */
function SampleRow({
  sample, busy, source, onOpen, onSource,
}: {
  sample: SampleInfo;
  busy: boolean;
  source: string | null;
  onOpen: () => void;
  onSource: () => void;
}) {
  return (
    <li className="sample-row" data-testid={`sample-${sample.id}`}>
      <div className="sample-main">
        <b>
          {sample.title}{" "}
          <span className="sample-level" title={LEVEL[sample.observability].hint}>
            {sample.observability}
          </span>
        </b>
        <span className="muted" title={sample.watch.join("\n")}>
          {sample.summary}
        </span>
      </div>
      <button className="primary" disabled={busy} onClick={onOpen}
        data-testid={`open-${sample.id}`}>
        Open
      </button>
      <button onClick={onSource} data-testid={`source-${sample.id}`}>
        {source !== null ? "Hide source" : "View source"}
      </button>
      {source !== null && (
        <>
          {sample.watch.length > 0 && (
            <ul className="sample-watch">
              {sample.watch.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          <pre className="sample-code" data-testid="sample-code">
            <code>{source}</code>
          </pre>
        </>
      )}
    </li>
  );
}

/** A collapsible group of examples. The first group starts open. */
function SampleGroup({
  id, title, samples, startOpen, busy, sourceId, sourceText, onOpen, onSource,
}: {
  id: string;
  title: string;
  samples: SampleInfo[];
  startOpen: boolean;
  busy: boolean;
  sourceId: string | null;
  sourceText: string | null;
  onOpen: (sample: SampleInfo) => void;
  onSource: (id: string) => void;
}) {
  const [open, setOpen] = useState(startOpen);
  if (samples.length === 0) return null;
  return (
    <details
      className="sample-group" open={open} data-testid={`group-${id}`}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        {title} <small>{samples.length}</small>
      </summary>
      <ul className="sample-list">
        {samples.map((s) => (
          <SampleRow
            key={s.id} sample={s} busy={busy}
            source={sourceId === s.id ? sourceText : null}
            onOpen={() => onOpen(s)} onSource={() => onSource(s.id)}
          />
        ))}
      </ul>
    </details>
  );
}

/** Bundled, pre-recorded examples. Opening one does not run any program. */
export function Gallery({ session, onOpen, busy }: Props) {
  const [source, setSource] = useState<{ id: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const byId = new Map(session.samples.map((s) => [s.id, s]));
  const listed = new Set(GROUPS.flatMap((g) => g.ids));
  const groups = GROUPS.map((g, i) => ({
    ...g,
    samples: [
      ...g.ids.map((id) => byId.get(id)).filter((s) => s !== undefined),
      ...(i === GROUPS.length - 1
        ? session.samples.filter((s) => !listed.has(s.id))
        : []),
    ],
  }));
  const toggleSource = async (id: string) => {
    if (source?.id === id) return setSource(null);
    try {
      setSource({ id, text: await sampleSource(id) });
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <section className="gallery" aria-label="Examples">
      <h2>Examples <small>real recordings, nothing is run when you open them</small></h2>
      {groups.map((g, i) => (
        <SampleGroup
          key={g.id} id={g.id} title={g.title} samples={g.samples}
          startOpen={i === 0} busy={busy}
          sourceId={source?.id ?? null} sourceText={source?.text ?? null}
          onOpen={onOpen} onSource={toggleSource}
        />
      ))}
      {error && <p className="warning">{error}</p>}
      {session.planned.length > 0 && (
        <p className="planned muted">
          Planned, not yet supported:{" "}
          {session.planned.map((p, i) => (
            <span key={p.title} title={`needs ${p.needs}`}>
              {i > 0 && " · "}{p.title}
            </span>
          ))}
        </p>
      )}
    </section>
  );
}
