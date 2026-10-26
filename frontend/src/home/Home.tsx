import { useRef, useState } from "react";
import { openSample, toBase64, uploadTrace, uploadWorkspace } from "../api/client";
import { collectDrop, collectInput, type PickedFile } from "../api/readDrop";
import type { SampleInfo, SessionInfo, WorkspaceInfo } from "../api/types";
import { Gallery } from "./Gallery";
import { RunPanel } from "./RunPanel";

interface Props {
  session: SessionInfo;
  onOpenTrace: () => void;
  onCompare: () => void;
  /** Present when a recording is already loaded. */
  onBack: (() => void) | null;
  onToggleTheme: () => void;
}

type Pending = { workspace: WorkspaceInfo | null; title: string } | null;

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Drop zone, run panel and example gallery. */
export function Home({ session, onOpenTrace, onCompare, onBack, onToggleTheme }: Props) {
  const [pending, setPending] = useState<Pending>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const dirInput = useRef<HTMLInputElement | null>(null);

  const guarded = async (job: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await job(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };

  const handleFiles = async (files: PickedFile[]) => {
    const trace = files.find((f) => f.path.endsWith(".concurim"));
    if (trace && files.length === 1) {
      await uploadTrace(trace.file, trace.file.name);
      onOpenTrace();
      return;
    }
    if (!files.some((f) => f.path.endsWith(".py"))) {
      throw new Error("Drop a .py file, a folder with Python code, or a .concurim recording.");
    }
    const payload = await Promise.all(
      files.map(async (f) => ({ path: f.path, data: await toBase64(f.file) })));
    const workspace = await uploadWorkspace(payload);
    const title = files.length === 1 ? files[0].path : `${workspace.suggested} (+${files.length - 1} files)`;
    setPending({ workspace, title });
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setOver(false);
    const dropped = collectDrop(e.dataTransfer); // read before the event ends
    guarded(async () => handleFiles(await dropped));
  };
  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files;
    if (list?.length) guarded(async () => handleFiles(collectInput(list)));
    e.target.value = "";
  };
  const openExample = (s: SampleInfo) => guarded(async () => {
    await openSample(s.id);
    onOpenTrace();
  });

  return (
    <div className="home" data-testid="home-screen">
      <header className="top">
        <div className="brand"><b>Concurim</b><span>See how Python runs together</span></div>
        <div className="meta">
          {onBack && (
            <button className="link" onClick={onBack} data-testid="back-to-recording">
              ← Back to “{session.label}”
            </button>
          )}
          <button className="link" onClick={onCompare} data-testid="open-compare">
            Compare two recordings
          </button>
          <button className="link" onClick={onToggleTheme} aria-label="Toggle theme">◐</button>
        </div>
      </header>
      <main>
        <section
          className="dropzone" data-over={over || undefined} data-testid="dropzone"
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)} onDrop={onDrop}
        >
          <h1>Drag in a Python program, record it, and watch its concurrency unfold.</h1>
          <p>
            Drop a <code>.py</code> file, a project folder, or a <code>.concurim</code> recording.
          </p>
          <div className="actions">
            <button onClick={() => fileInput.current?.click()} disabled={busy}>Choose file…</button>
            <button onClick={() => dirInput.current?.click()} disabled={busy}>Choose folder…</button>
            <button onClick={() => setPending({ workspace: null, title: "a file on this computer" })}
              disabled={busy} data-testid="run-from-path">Run a file by path…</button>
          </div>
          <input ref={fileInput} type="file" accept=".py,.concurim" hidden
            data-testid="file-input" onChange={onPick} />
          <input ref={dirInput} type="file" hidden onChange={onPick} data-testid="dir-input"
            {...{ webkitdirectory: "" }} />
          {busy && <p className="muted">Working…</p>}
          {error && <p className="warning" data-testid="home-error">{error}</p>}
          <p className="muted small">
            Everything stays on this computer. A dropped program is never run
            until you review the plan and click “Record execution”.
          </p>
        </section>
        {pending && (
          <RunPanel session={session} workspace={pending.workspace} title={pending.title}
            onOpenTrace={onOpenTrace} onClose={() => setPending(null)} />
        )}
        <Gallery session={session} onOpen={openExample} busy={busy} />
      </main>
    </div>
  );
}
