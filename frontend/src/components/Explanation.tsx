import type { Frame, TraceEvent } from "../models/replay";

/** Plain-language account of the current event, with honesty labels. */
export function Explanation({ frame, event }: { frame: Frame; event: TraceEvent }) {
  const ex = frame.explanation;
  return (
    <section className="card explanation" data-tone={ex.tone}
      data-testid="explanation">
      <header>
        <span className="tone-dot" />
        <h2>{ex.title}</h2>
        <span className="tag" title="Derived directly from a recorded event">observed</span>
      </header>
      <p data-testid="explanation-text">{ex.text}</p>
      {ex.inferred.map((t) => (
        <p key={t} className="inferred">
          <span className="tag inferred-tag">inferred</span> {t}
        </p>
      ))}
      <footer>
        event {event.sequence} · {event.event_type}
      </footer>
    </section>
  );
}
