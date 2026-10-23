import { useEffect, useMemo, useRef, useState } from "react";
import type { Replay } from "../models/replay";

const WINDOW = 200;

/** Filterable list of all events; click to seek. */
export function EventLog({ replay, index, onSeek }: {
  replay: Replay; index: number; onSeek: (i: number) => void;
}) {
  const [filter, setFilter] = useState("");
  const current = useRef<HTMLLIElement | null>(null);
  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return replay.events
      .map((e, i) => ({ e, i }))
      .filter(({ e }) => {
        if (!needle) return true;
        const th = e.thread_id ? replay.entities.threads[e.thread_id]?.name ?? "" : "";
        return `${e.event_type} ${th} ${e.object_id ?? ""}`.toLowerCase().includes(needle);
      });
  }, [replay, filter]);
  const visible = rows.filter(({ i }) => Math.abs(i - index) <= WINDOW);

  useEffect(() => {
    current.current?.scrollIntoView({ block: "nearest" });
  }, [index]);

  return (
    <div className="eventlog">
      <input type="search" placeholder="filter by type, thread, object"
        value={filter} onChange={(e) => setFilter(e.target.value)}
        aria-label="Filter events" />
      <ul data-testid="event-log">
        {visible.map(({ e, i }) => (
          <li key={i} ref={i === index ? current : undefined}
            data-current={i === index || undefined}
            data-future={i > index || undefined}>
            <button className="link" onClick={() => onSeek(i)}>
              <span className="n">{i + 1}</span>
              <span className="t">{e.event_type}</span>
              <span className="who">
                {e.thread_id ? replay.entities.threads[e.thread_id]?.name : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
