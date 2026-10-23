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
  threads: {
    name: "Automatic: threads only",
    hint: "No Concurim imports; only thread lifetimes are observed.",
  },
};

interface Props {
  session: SessionInfo;
  onOpen: (sample: SampleInfo) => void;
  busy: boolean;
}

/** Bundled, pre-recorded examples. Opening one does not run any program. */
export function Gallery({ session, onOpen, busy }: Props) {
  const [source, setSource] = useState<{ id: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
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
      <div className="cards">
        {session.samples.map((s) => (
          <article key={s.id} className="card sample" data-testid={`sample-${s.id}`}>
            <span className="tag" title={LEVEL[s.observability].hint}>
              {LEVEL[s.observability].name}
            </span>
            <h3>{s.title}</h3>
            <p>{s.summary}</p>
            <ul>{s.watch.map((w) => <li key={w}>{w}</li>)}</ul>
            <footer>
              <button className="primary" disabled={busy}
                onClick={() => onOpen(s)} data-testid={`open-${s.id}`}>
                Open
              </button>
              <button onClick={() => toggleSource(s.id)}
                data-testid={`source-${s.id}`}>
                {source?.id === s.id ? "Hide source" : "View source"}
              </button>
            </footer>
            {source?.id === s.id && (
              <pre className="sample-code" data-testid="sample-code"><code>{source.text}</code></pre>
            )}
          </article>
        ))}
      </div>
      {error && <p className="warning">{error}</p>}
      <p className="planned muted">
        Planned, not yet supported:{" "}
        {session.planned.map((p, i) => (
          <span key={p.title} title={`needs ${p.needs}`}>
            {i > 0 && " · "}{p.title}
          </span>
        ))}
      </p>
    </section>
  );
}
