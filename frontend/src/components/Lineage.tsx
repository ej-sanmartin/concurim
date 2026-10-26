import { familyRows, hasLineage, lineageRoots } from "../models/lineage";
import type { Replay } from "../models/replay";
import type { Selection } from "../models/selection";
import type { WorldState } from "../models/states";

interface Props {
  replay: Replay;
  world: WorldState;
  index: number;
  selection: Selection;
  /** The item shown by the current event, when it has one. */
  currentObject: string | null;
  onFocus: (id: string) => void;
  onSeek: (i: number) => void;
}

/** Which item to walk from: the selected one, else the current event's. */
function focusOf(replay: Replay, selection: Selection, current: string | null) {
  const chosen = selection?.kind === "object" ? selection.id : current;
  const inChain = (id: string | null) =>
    !!id && familyRows(replay, id).length > 1;
  if (inChain(chosen)) return chosen!;
  return lineageRoots(replay)[0] ?? null;
}

/**
 * Walks chains of items linked by `put(..., derived_from=...)`. The links are
 * explicit annotations from the program, never guessed from values.
 */
export function Lineage({ replay, world, index, selection, currentObject, onFocus, onSeek }: Props) {
  if (!hasLineage(replay)) {
    return (
      <p className="muted" data-testid="lineage-empty">
        No item links were recorded. Pass <code>derived_from=item.object_id</code>{" "}
        to <code>TracedQueue.put</code> when a new item is made from another one.
      </p>
    );
  }
  const focus = focusOf(replay, selection, currentObject)!;
  const rows = familyRows(replay, focus);
  const roots = lineageRoots(replay);
  return (
    <div className="lineage" data-testid="lineage">
      {roots.length > 1 && (
        <p className="muted">{roots.length} chains. Pick an item to see its own.</p>
      )}
      <ul>
        {rows.map((r) => {
          const o = replay.entities.objects[r.id];
          const first = o?.journey[0]?.[0] ?? null;
          const phase = world.objects[r.id]?.phase;
          return (
            <li key={r.id} style={{ paddingLeft: r.depth * 16 }}
              data-focus={r.id === focus || undefined}
              data-unrelated={!r.related || undefined}
              data-future={(first === null || first > index) || undefined}>
              {r.known ? (
                <button className="link" onClick={() => onFocus(r.id)}>
                  {o.preview ?? o.type ?? r.id}
                </button>
              ) : <span className="muted">unknown item</span>}{" "}
              <small>{r.id}</small>
              {" · "}{phase ?? "not created yet"}
              {first !== null && (
                <>{" · "}
                  <button className="link" onClick={() => onSeek(first)}>
                    created at event {first + 1}
                  </button>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
