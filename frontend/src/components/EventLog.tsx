import { useEffect, useMemo, useRef, useState } from "react";
import { foldRows } from "../models/fold";
import { nameOf } from "../models/names";
import { actorOf, type Replay } from "../models/replay";

const WINDOW = 200;

/** Filterable list of all events; click to seek. Look-alike runs fold. */
export function EventLog({ replay, index, onSeek }: {
  replay: Replay; index: number; onSeek: (i: number) => void;
}) {
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set());
  const current = useRef<HTMLLIElement | null>(null);
  const matching = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const out: number[] = [];
    replay.events.forEach((e, i) => {
      const who = nameOf(replay, actorOf(e));
      if (!needle || `${e.event_type} ${who} ${e.object_id ?? ""}`.toLowerCase().includes(needle)) {
        out.push(i);
      }
    });
    return out;
  }, [replay, filter]);
  const rows = foldRows(replay.events, matching, open, index);
  const visible = rows.filter((r) => Math.abs(r.index - index) <= WINDOW);
  const toggle = (first: number) => setOpen((old) => {
    const next = new Set(old);
    if (!next.delete(first)) next.add(first);
    return next;
  });

  useEffect(() => {
    current.current?.scrollIntoView({ block: "nearest" });
  }, [index]);

  return (
    <div className="eventlog">
      <input type="search" placeholder="filter by type, thread, object"
        value={filter} onChange={(e) => setFilter(e.target.value)}
        aria-label="Filter events" />
      <ul data-testid="event-log">
        {visible.map(({ index: i, fold }) => {
          const e = replay.events[i];
          return (
            <li key={i} ref={i === index ? current : undefined}
              data-current={i === index || undefined}
              data-future={i > index || undefined}>
              <button className="link" onClick={() => onSeek(i)}>
                <span className="n">{i + 1}</span>
                <span className="t">{e.event_type}</span>
                <span className="who">{actorOf(e) ? nameOf(replay, actorOf(e)) : ""}</span>
              </button>
              {fold && (
                <button className="fold" data-testid="fold" aria-expanded={fold.open}
                  title={fold.open ? "Fold this run"
                    : `${fold.repeats} repetitions of ${fold.period} event${fold.period > 1 ? "s" : ""}`}
                  onClick={() => toggle(i)}>
                  {fold.open ? "▾" : `×${fold.repeats}`}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
