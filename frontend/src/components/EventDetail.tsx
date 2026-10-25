import { actorOf, type Replay, type TraceEvent } from "../models/replay";

interface Props {
  replay: Replay;
  event: TraceEvent;
  indexById: Map<string, number>;
  onSeek: (i: number) => void;
  onOpenCode: () => void;
}

/** Location of the event, as a shortcut into Code mode. */
function sourceCell(event: TraceEvent, onOpenCode: () => void): React.ReactNode {
  const src = event.source;
  if (!src) return "not recorded";
  const where = `${src.file}:${src.line} in ${src.function}`;
  return (
    <button className="link" data-testid="open-code" title="Show in Code"
      onClick={onOpenCode}>
      {where}
    </button>
  );
}

function fmtTime(ns: number): string {
  return ns < 1e6 ? `${(ns / 1e3).toFixed(0)} µs` : `${(ns / 1e6).toFixed(1)} ms`;
}

/** Raw fields of the current event; every value is rendered as text. */
export function EventDetail({ replay, event, indexById, onSeek, onOpenCode }: Props) {
  const who = actorOf(event);
  const thread = who ? replay.entities.threads[who] : null;
  const queue = event.resource_id
    ? replay.entities.queues[event.resource_id] ?? replay.entities.syncs[event.resource_id]
    : null;
  const cause = event.caused_by ? indexById.get(event.caused_by) : undefined;
  const rows: [string, React.ReactNode][] = [
    ["time", fmtTime(event.timestamp_ns)],
    [thread?.kind === "task" ? "task" : "thread", thread ? `${thread.name} (${thread.id})` : "–"],
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
    ["source", sourceCell(event, onOpenCode)],
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
