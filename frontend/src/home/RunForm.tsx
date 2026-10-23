import type { AutoLevel, Interpreter, WorkspaceInfo } from "../api/types";

export interface RunOptions {
  entry: string;
  scriptPath: string;
  args: string;
  interpreter: string;
  auto: AutoLevel;
  includeSource: boolean;
  preview: boolean;
}

const LEVELS: { id: AutoLevel; name: string; help: string }[] = [
  { id: "threads", name: "Threads (default)",
    help: "Records when every thread starts and finishes. Queues are not observed." },
  { id: "queues", name: "Threads + queues",
    help: "Also records queue.Queue objects created during the run. Opt-in: it " +
      "temporarily replaces queue.Queue while recording." },
  { id: "sync", name: "+ locks, semaphores, thread pools",
    help: "Also records threading.Lock, RLock, Semaphore and " +
      "ThreadPoolExecutor objects the program creates. While recording, " +
      "isinstance(x, threading.Lock) is False for those locks." },
  { id: "asyncio", name: "+ asyncio",
    help: "Also records asyncio tasks, queues, locks and semaphores. " +
      "Tasks are recorded when they run; uvloop is not supported." },
  { id: "none", name: "Concurim objects only",
    help: "Records only TracedQueue / TracedThread used by the program." },
];

/** Short level names for run summaries. */
export const LEVEL_NAME = Object.fromEntries(
  LEVELS.map((l) => [l.id, l.name]),
) as Record<AutoLevel, string>;

interface Props {
  options: RunOptions;
  onChange: (o: RunOptions) => void;
  workspace: WorkspaceInfo | null;
  interpreters: Interpreter[];
}

/** The choices that shape a recording. Nothing here runs anything. */
export function RunForm({ options, onChange, workspace, interpreters }: Props) {
  const set = <K extends keyof RunOptions>(key: K, value: RunOptions[K]) =>
    onChange({ ...options, [key]: value });
  const known = interpreters.some((i) => i.path === options.interpreter);
  return (
    <fieldset className="runform">
      {workspace ? (
        workspace.python_files.length > 1 && (
          <label>Entry point
            <select value={options.entry} data-testid="entry"
              onChange={(e) => set("entry", e.target.value)}>
              {workspace.python_files.map((f) => (
                <option key={f} value={f}>
                  {f}{workspace.entries.includes(f) ? "" : " (no __main__ guard)"}
                </option>
              ))}
            </select>
          </label>
        )
      ) : (
        <label>Python file on this computer
          <input value={options.scriptPath} data-testid="script-path"
            placeholder="/path/to/main.py"
            onChange={(e) => set("scriptPath", e.target.value)} />
        </label>
      )}
      <label>Arguments
        <input value={options.args} data-testid="args" placeholder="--flag value"
          onChange={(e) => set("args", e.target.value)} />
      </label>
      <label>Python interpreter
        <select value={known ? options.interpreter : "__other"}
          data-testid="interpreter"
          onChange={(e) => set("interpreter", e.target.value === "__other" ? "" : e.target.value)}>
          {interpreters.map((i) => (
            <option key={i.path} value={i.path}>
              {i.label}{i.version ? ` ${i.version}` : ""}{i.supported === false ? " (too old)" : ""}
              {" — "}{i.path}
            </option>
          ))}
          <option value="__other">Other path…</option>
        </select>
        {!known && (
          <input value={options.interpreter} placeholder="/path/to/python"
            data-testid="interpreter-path"
            onChange={(e) => set("interpreter", e.target.value)} />
        )}
        <small>Needs Python 3.13+. Dependencies come from this interpreter's environment.</small>
      </label>
      <div className="levels" role="radiogroup" aria-label="Instrumentation">
        <span>What to observe</span>
        {LEVELS.map((l) => (
          <label key={l.id} className="level">
            <input type="radio" name="level" checked={options.auto === l.id}
              data-testid={`level-${l.id}`} onChange={() => set("auto", l.id)} />
            <b>{l.name}</b> <small>{l.help}</small>
          </label>
        ))}
      </div>
      <label className="check">
        <input type="checkbox" checked={options.includeSource}
          data-testid="include-source"
          onChange={(e) => set("includeSource", e.target.checked)} />
        Store source files in the recording (shown in the Source tab)
      </label>
      <label className="check">
        <input type="checkbox" checked={options.preview}
          data-testid="preview"
          onChange={(e) => set("preview", e.target.checked)} />
        Store short previews of simple values put on queues
      </label>
    </fieldset>
  );
}
