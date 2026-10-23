import { m } from "motion/react";
import { objectColor, objectLabel } from "../animations/palette";
import type { Selection } from "../models/selection";
import type { WorldState } from "../models/states";
import { handSlots, objectPoint, type Geometry } from "./geometry";

const EASE = [0.22, 1, 0.36, 1] as const;

interface Props {
  world: WorldState;
  geo: Geometry;
  selection: Selection;
  motionMs: number;
  onSelect: (s: Selection) => void;
}

/**
 * Data items as tokens. Each token's target is a pure function of the
 * replayed state (see ``objectPoint``); Motion only interpolates toward it,
 * so any seek or backward step lands on exactly the same picture.
 */
export function Tokens({ world, geo, selection, motionMs, onSelect }: Props) {
  const hands = handSlots(world);
  return (
    <>
      {Object.values(world.objects).map((o) => {
        const pt = objectPoint(o.id, world, geo, hands);
        if (!pt) return null;
        const gone = o.phase === "released" || o.phase === "discarded";
        const holder = o.at ? world.threads[o.at] : undefined;
        const blocked = o.phase === "putting" && holder?.status === "waiting";
        const picked = selection?.kind === "object" && selection.id === o.id;
        return (
          <m.div
            key={o.id}
            className="token"
            data-testid={`token-${o.id}`}
            data-phase={o.phase}
            data-hidden={gone || undefined}
            data-blocked={blocked || undefined}
            data-selected={picked || undefined}
            title={`${o.id}${o.preview ? ` (${o.preview})` : ""} — ${o.phase}`}
            style={{ background: objectColor(o.id) }}
            initial={{ x: pt.x, y: pt.y, opacity: 0, scale: 0.4 }}
            animate={{
              x: pt.x, y: pt.y,
              opacity: gone ? 0 : 1, scale: gone ? 0.5 : 1,
            }}
            transition={{ duration: motionMs / 1000, ease: EASE }}
            onClick={(e) => {
              e.stopPropagation();
              onSelect({ kind: "object", id: o.id });
            }}
          >
            {objectLabel(o.id)}
          </m.div>
        );
      })}
    </>
  );
}
