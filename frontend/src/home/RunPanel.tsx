import { useEffect, useRef, useState } from "react";
import { cancelRun, getRun, openSnapshot, planRun, startRun } from "../api/client";
import type { RunPlan, RunStatus, SessionInfo, WorkspaceInfo } from "../api/types";
import { LEVEL_NAME, RunForm, type RunOptions } from "./RunForm";
import { RunProgress } from "./RunProgress";

const POLL_MS = 400;

interface Props {
  session: SessionInfo;
  /** Set when files were dropped; ``null`` to run a file already on disk. */
  workspace: WorkspaceInfo | null;
  title: string;
  onOpenTrace: () => void;
  onClose: () => void;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * Configure, review and run a program under the recorder. The plan shown is
 * built by the server; nothing executes until "Record execution" is clicked.
 */
export function RunPanel({ session, workspace, title, onOpenTrace, onClose }: Props) {
  const [options, setOptions] = useState<RunOptions>(() => ({
    entry: workspace?.suggested ?? "",
    scriptPath: "",
    args: "",
    interpreter: session.interpreters.find((i) => i.supported !== false)?.path ?? "",
    auto: "threads",
    includeSource: true,
    preview: false,
  }));
  const [plan, setPlan] = useState<{ plan: RunPlan; key: string } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const opened = useRef(false);
  const key = JSON.stringify(options);

  useEffect(() => {
    if (run) return;
    const ready = workspace ? !!options.entry : !!options.scriptPath;
    if (!ready) { setPlan(null); return; }
    const timer = window.setTimeout(() => {
      planRun({
        workspace_id: workspace?.id, entry: workspace ? options.entry : undefined,
        script_path: workspace ? undefined : options.scriptPath,
        args: options.args, interpreter: options.interpreter, auto: options.auto,
        include_source: options.includeSource, preview: options.preview,
      }).then((p) => { setPlan({ plan: p, key }); setProblem(null); })
        .catch((e) => { setPlan(null); setProblem(message(e)); });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [key, run, workspace]);

  useEffect(() => {
    if (run?.state !== "running") return;
    const timer = window.setInterval(() => {
      getRun(run.id).then(setRun).catch((e) => setProblem(message(e)));
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.state]);

  useEffect(() => {
    if (run?.state === "finished" && run.trace_ready && !opened.current) {
      opened.current = true;
      onOpenTrace();
    }
  }, [run, onOpenTrace]);

  const confirmed = plan && plan.key === key ? plan.plan : null;
  const selected = session.interpreters.find((i) => i.path === options.interpreter);
  const tooOld = selected?.supported === false;
  const record = () => {
    if (!confirmed) return;
    opened.current = false;
    startRun(confirmed.id).then(setRun).catch((e) => setProblem(message(e)));
  };

  return (
    <section className="card runpanel" aria-label="Record a program" data-testid="run-panel">
      <header>
        <h2>Record <code>{title}</code></h2>
        <button className="link" onClick={onClose} aria-label="Close">✕</button>
      </header>
      {run ? (
        <RunProgress run={run} onCancel={() => cancelRun(run.id).then(setRun)}
          onOpen={onOpenTrace}
          onWatch={() => {
            openSnapshot(run.id).then(() => onOpenTrace())
              .catch((e) => setProblem(message(e)));
          }}
          onBack={() => setRun(null)} />
      ) : (
        <>
          <RunForm options={options} onChange={setOptions} workspace={workspace}
            interpreters={session.interpreters} />
          {problem && <p className="warning" data-testid="plan-problem">{problem}</p>}
          {tooOld && <p className="warning">This interpreter is older than Python 3.13.</p>}
          {confirmed && <PlanCard plan={confirmed} />}
          <div className="actions">
            <button className="primary" disabled={!confirmed || tooOld}
              onClick={record} data-testid="record">
              Record execution
            </button>
            <span className="muted">
              Runs on your computer with your permissions. Concurim does not
              sandbox the program.
            </span>
          </div>
        </>
      )}
    </section>
  );
}

/** Exactly what will run, as computed by the server. */
function PlanCard({ plan }: { plan: RunPlan }) {
  return (
    <dl className="plan" data-testid="plan">
      <dt>Interpreter</dt><dd><code>{plan.interpreter}</code></dd>
      <dt>Script</dt><dd><code>{plan.script}</code></dd>
      <dt>Arguments</dt>
      <dd><code>{plan.args.length ? plan.args.join(" ") : "(none)"}</code></dd>
      <dt>Working directory</dt><dd><code>{plan.cwd}</code></dd>
      <dt>Observing</dt><dd>{LEVEL_NAME[plan.auto]}</dd>
      <dt>Exact command</dt>
      <dd><details><summary>show</summary><code>{plan.command}</code></details></dd>
    </dl>
  );
}
