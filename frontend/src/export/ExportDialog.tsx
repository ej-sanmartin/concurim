import { useEffect, useRef, useState } from "react";
import {
  cancelExport, exportFileUrl, getExport, startExport,
} from "../api/client";
import type { ExportCaps, ExportStatus } from "../api/types";
import { ExportFields } from "./ExportFields";
import {
  defaultForm, problem, toRequest, type ExportForm, type View,
} from "./options";

interface Props {
  caps: ExportCaps;
  /** The viewer's current mode and event, used as the starting point. */
  view: View;
  index: number;
  total: number;
  onClose: () => void;
}

const POLL_MS = 400;
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * Modal for turning the open recording into a clip. The server renders it
 * (headless browser + ffmpeg) and the finished file downloads from here.
 * Nothing in this dialog runs the recorded program.
 */
export function ExportDialog({ caps, view, index, total, onClose }: Props) {
  const [form, setForm] = useState<ExportForm>(
    () => defaultForm(view, total, caps));
  const [job, setJob] = useState<ExportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const running = job?.state === "running";
  const blocked = problem(form, total, caps);

  useEffect(() => { root.current?.focus(); }, []);
  useEffect(() => {
    if (!job || job.state !== "running") return;
    const id = window.setInterval(() => {
      getExport(job.id).then(setJob).catch((e) => setError(message(e)));
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [job]);

  const start = () => {
    setError(null);
    startExport(toRequest(form)).then(setJob).catch((e) => setError(message(e)));
  };
  const stop = () => {
    if (job) cancelExport(job.id).then(setJob).catch((e) => setError(message(e)));
  };
  const close = () => { if (!running) onClose(); };
  const percent = job && job.total ? Math.round((100 * job.done) / job.total) : 0;

  return (
    <div className="modal-backdrop" onMouseDown={(e) => {
      if (e.target === e.currentTarget) close();
    }}>
      <div className="modal export-dialog" role="dialog" aria-modal="true"
        aria-labelledby="export-title" ref={root} tabIndex={-1}
        data-testid="export-dialog"
        onKeyDown={(e) => {
          e.stopPropagation(); // viewer shortcuts must not fire in here
          if (e.key === "Escape") close();
        }}>
        <header>
          <h2 id="export-title">Export a clip</h2>
          <button className="link" onClick={close} disabled={running}
            aria-label="Close">✕</button>
        </header>

        {job === null && (
          <>
            {(!caps.browser || (!caps.ffmpeg && form.format !== "png")) && (
              <p className="export-note" role="alert">{blocked}</p>
            )}
            <ExportFields form={form} caps={caps} total={total}
              current={index + 1}
              onChange={(patch) => setForm({ ...form, ...patch })} />
            <p className="export-warning">
              A clip shows everything in the picture: file paths, thread
              names and, with code, your source. Review it before sharing.
            </p>
            {error && <p className="export-error" role="alert">{error}</p>}
            <footer>
              <button onClick={onClose}>Cancel</button>
              <button className="primary" onClick={start} disabled={!!blocked}
                data-testid="export-start-button" title={blocked ?? undefined}>
                Export</button>
            </footer>
          </>
        )}

        {running && (
          <div data-testid="export-progress">
            <p>Rendering event {job.done} of {job.total || "…"}</p>
            <progress max={100} value={percent} aria-label="Export progress" />
            <footer><button onClick={stop}>Cancel export</button></footer>
          </div>
        )}

        {job?.state === "done" && (
          <div data-testid="export-done">
            <p>Your clip is ready.</p>
            <footer>
              <button onClick={() => setJob(null)}>Change options</button>
              <a className="button primary" href={exportFileUrl(job.id)}
                download={job.filename} data-testid="export-download">
                Download {job.filename}</a>
            </footer>
          </div>
        )}

        {(job?.state === "failed" || job?.state === "cancelled") && (
          <div data-testid="export-failed">
            <p className="export-error" role="alert">
              {job.state === "cancelled" ? "Export cancelled." : job.error}
            </p>
            <footer><button onClick={() => setJob(null)}>Back to options</button></footer>
          </div>
        )}
      </div>
    </div>
  );
}
