import type { Replay } from "../models/replay";
import type { WorldState } from "../models/states";
import type { Selection } from "../models/selection";
import { STATUS_LABEL } from "../animations/palette";
import { nameOf } from "../models/names";
import { actorOf } from "../models/replay";

interface Props {
  replay: Replay;
  world: WorldState;
  index: number;
  selection: Selection;
  onSeek: (i: number) => void;
}

const MAX_ROWS = 60;

/** Identity, current state and history for the selected entity. */
export function Inspector({ replay, world, index, selection, onSeek }: Props) {
  if (!selection) {
    return <p className="muted">Click a thread, queue, lock, or item to inspect it.</p>;
  }
  const name = (id: string | null | undefined) => nameOf(replay, id);
  const history = replay.events
    .map((e, i) => ({ e, i }))
    .filter(({ e }) =>
      selection.kind === "thread" ? actorOf(e) === selection.id
        : selection.kind === "queue" || selection.kind === "sync" ? e.resource_id === selection.id
          : e.object_id === selection.id);
  let facts: [string, string][] = [];

  if (selection.kind === "thread") {
    const s = world.threads[selection.id];
    facts = s ? [
      ["state", `${STATUS_LABEL[s.status]} (${s.basis})`],
      ["waiting on", s.waiting_on ? `${s.waiting_on.op} ${name(s.waiting_on.resource)}` : "–"],
      ["received, not finished", s.holding.join(", ") || "–"],
      ["current work", s.work ?? "–"],
    ] : [["state", "not seen yet at this point"]];
  } else if (selection.kind === "sync") {
    const s = world.syncs[selection.id];
    const info = replay.entities.syncs[selection.id];
    facts = s ? [
      ["kind", info.kind],
      ...(info.kind === "semaphore"
        ? [["permits free", `${s.value} of ${s.capacity}`] as [string, string]] : []),
      ...(info.kind === "event"
        ? [["flag", s.is_set ? "set" : "not set"] as [string, string]] : []),
      ...(info.kind === "barrier"
        ? [["party", `${s.waiters.length} of ${s.capacity} waiting`] as [string, string],
          ["broken", s.broken ? "yes" : "no"] as [string, string]] : []),
      ...(info.kind === "condition"
        ? [["lock", s.lock ? name(s.lock) : "not recorded"] as [string, string],
          ["notified, not yet resumed", String(s.notified)] as [string, string]] : []),
      ...(info.kind === "taskgroup"
        ? [["tasks", `${s.running} running of ${s.members.length}`] as [string, string],
          ["members", s.members.map(name).join(", ") || "–"] as [string, string]] : []),
      ...(["lock", "rlock", "semaphore"].includes(info.kind)
        ? [["held by", s.holders.map(name).join(", ") || "–"] as [string, string]] : []),
      ["waiting", s.waiters.map((b) => name(b.thread)).join(", ") || "–"],
    ] : [["state", "not created yet at this point"]];
  } else if (selection.kind === "queue") {
    const q = world.queues[selection.id];
    facts = q ? [
      ...(q.kind === "executor"
        ? [["workers running", `${q.running} of ${q.workers}`] as [string, string]] : []),
      ["capacity", q.maxsize > 0 ? String(q.maxsize) : "unbounded"],
      ["queued (front first)", q.size === 0 ? "empty" : q.items.join(", ") + (q.size > q.items.length ? ` … (+${q.size - q.items.length})` : "")],
      ["unfinished tasks", String(q.unfinished)],
      ["blocked producers", q.blocked_puts.map((b) => name(b.thread)).join(", ") || "–"],
      ["blocked consumers", q.blocked_gets.map((b) => name(b.thread)).join(", ") || "–"],
      ["in join()", q.joiners.map(name).join(", ") || "–"],
      ["shutdown", q.shutdown ?? "no"],
    ] : [["state", "not created yet at this point"]];
  } else {
    const o = world.objects[selection.id];
    const ent = replay.entities.objects[selection.id];
    facts = [
      ["type", ent?.type ?? "–"],
      ["preview", ent?.preview ?? "not recorded"],
      ["now", o ? `${o.phase} @ ${name(o.at)}` : "not created yet"],
      ["derived from", ent?.parent ?? "–"],
    ];
  }
  const journey = selection.kind === "object"
    ? replay.entities.objects[selection.id]?.journey ?? [] : [];

  return (
    <div className="inspector" data-testid="inspector">
      <h3>{name(selection.id)} <small>{selection.id}</small></h3>
      <table><tbody>
        {facts.map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}
      </tbody></table>
      {journey.length > 0 && (
        <>
          <h4>Journey</h4>
          <ol className="journey">
            {journey.map(([i, phase, at]) => (
              <li key={i} data-future={i > index || undefined}>
                <button className="link" onClick={() => onSeek(i)}>
                  event {i + 1}
                </button>{" "}
                {phase} @ {name(at)}
              </li>
            ))}
          </ol>
        </>
      )}
      <h4>History <small>({history.length})</small></h4>
      <ul className="history">
        {history.slice(0, MAX_ROWS).map(({ e, i }) => (
          <li key={i} data-future={i > index || undefined}
            data-current={i === index || undefined}>
            <button className="link" onClick={() => onSeek(i)}>{i + 1}</button>{" "}
            {e.event_type}
          </li>
        ))}
        {history.length > MAX_ROWS && <li className="muted">… {history.length - MAX_ROWS} more</li>}
      </ul>
    </div>
  );
}
