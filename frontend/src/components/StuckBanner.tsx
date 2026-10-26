import type { Replay } from "../models/replay";

interface Props {
  replay: Replay;
  onShow: (index: number) => void;
}

/**
 * The run stopped while actors were still blocked, or this picture is a
 * snapshot of a run that had not finished. A cleared cycle stays in the
 * Trace tab; this bar is only for a picture that still ends there.
 */
export function StuckBanner({ replay, onShow }: Props) {
  const wait = replay.wait_for;
  const outcome = replay.metadata.program?.outcome as string | undefined;
  const open = wait?.cycles ?? [];
  const episode = wait?.episodes?.find((ep) => ep.resolved_at === null);
  const interrupted = outcome === "interrupted";
  const running = outcome === "running";
  if (!interrupted && !running && open.length === 0) return null;

  const names = open.map(phrase).filter(Boolean).join(" ");
  let text = names;
  if (interrupted) {
    text = names
      ? `${names} The recording stops at the last observed event.`
      : "Recording stopped before the program finished. The picture ends at the last observed event.";
  } else if (running) {
    text = names
      ? `${names} This snapshot was taken while the run was still going.`
      : "This is a snapshot of a run that was still going.";
  }
  const at = episode?.at ?? replay.events.length - 1;
  return (
    <div className="stuck" data-testid="stuck-banner" role="status">
      <p>{text}</p>
      {replay.events.length > 0 && (
        <button type="button" onClick={() => onShow(at)}
          data-testid="show-stuck">
          Show that moment
        </button>
      )}
    </div>
  );
}

/** One cycle, as a sentence. A single actor is waiting on a lock it holds. */
function phrase(cycle: string[]): string {
  if (cycle.length === 0) return "";
  if (cycle.length === 1) {
    return `${cycle[0]} is waiting for a lock it already holds.`;
  }
  const names = cycle.length === 2
    ? `${cycle[0]} and ${cycle[1]}`
    : `${cycle.slice(0, -1).join(", ")}, and ${cycle[cycle.length - 1]}`;
  return `${names} are waiting on locks one another holds.`;
}
