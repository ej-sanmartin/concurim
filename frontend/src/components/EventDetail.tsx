import type { Replay, TraceEvent } from "../models/replay";

interface Props {
  replay: Replay;
  event: TraceEvent;
  indexById: Map<string, number>;
  onSeek: (i: number) => void;
}

function fmtTime(ns: number): string {
  return ns < 1e6 ? `${(ns / 1e3).toFixed(0)} µs` : `${(ns / 1e6).toFixed(1)} ms`;
}

/** Raw fields of the current event; every value is rendered as text. */
export function EventDetail({ replay, event, indexById, onSeek }: Props) {
  const thread = event.thread_id ? replay.entities.threads[event.thread_id] : null;
  const queue = event.resource_id ? replay.entities.queues[event.resource_id] : null;
  const cause = event.caused_by ? indexById.get(event.caused_by) : undefined;
  const rows: [string, React.ReactNode][] = [
    ["time", fmtTime(event.timestamp_ns)],
    ["thread", thread ? `${thread.name} (${thread.id})` : "–"],
    ["resource", queue ? `${queue.name} (${queue.id})` : (event.resource_id ?? "–")],
    ["object", event.object_id ?? "–"],
    ["operation", event.operation_id ?? "–"],
    [
      "caused by",
      cause === undefined ? "–" : (
        <button className="link" onClick={() => onSeek(cause)}>
          event {cause + 1}
        </button>
      ),
    ],
    [
      "source",
      event.source
        ? `${event.source.file}:${event.source.line} in ${event.source.function}`
        : "not recorded",
    ],
  ];
  return (
    <div className="detail" data-testid="event-detail">
      <table>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}><th>{k}</th><td>{v}</td></tr>
          ))}
          {Object.entries(event.metadata ?? {}).map(([k, v]) => (
            <tr key={`m-${k}`} className="meta">
              <th>{k}</th><td>{String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
