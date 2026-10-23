import { useEffect, useRef } from "react";
import type { RunStatus } from "../api/types";

const TITLE: Record<RunStatus["state"], string> = {
  running: "Recording…",
  finished: "Finished",
  failed: "The program failed",
  cancelled: "Cancelled",
  error: "Could not start",
};

interface Props {
  run: RunStatus;
  onCancel: () => void;
  onOpen: () => void;
  onBack: () => void;
}

/** Live output of the program, its outcome, and what to do next. */
export function RunProgress({ run, onCancel, onOpen, onBack }: Props) {
  const out = useRef<HTMLPreElement | null>(null);
  useEffect(() => {
    out.current?.scrollTo({ top: out.current.scrollHeight });
  }, [run.output]);
  const done = run.state !== "running";
  return (
    <div className="runprogress" data-testid="run-progress" data-state={run.state}>
      <h3>
        {TITLE[run.state]}
        {run.exit_code !== null && <small> exit code {run.exit_code}</small>}
        {run.exception && <small> · raised {run.exception}</small>}
      </h3>
      {run.error && <p className="warning">{run.error}</p>}
      <pre ref={out} className="output" data-testid="run-output" tabIndex={0}>
        {run.output || (done ? "(the program printed nothing)" : "waiting for output…")}
      </pre>
      {run.output_truncated && <p className="muted">Showing the end of the output.</p>}
      <div className="actions">
        {!done && <button onClick={onCancel} data-testid="cancel-run">Cancel</button>}
        {done && run.trace_ready && (
          <button className="primary" onClick={onOpen} data-testid="open-recording">
            Open recording
          </button>
        )}
        {done && !run.trace_ready && (
          <span className="muted">No recording was produced.</span>
        )}
        {done && <button onClick={onBack}>Back</button>}
      </div>
    </div>
  );
}
