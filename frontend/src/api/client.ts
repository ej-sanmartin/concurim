import type { Replay } from "../models/replay";
import type {
  ExportRequest, ExportStatus, RunPlan, RunRequest, RunStatus, SessionInfo,
  WorkspaceInfo,
} from "./types";

/** The per-launch token the server embeds in the page it serves. */
function token(): string {
  return document.querySelector<HTMLMetaElement>(
    'meta[name="concurim-token"]')?.content ?? "";
}

async function call<T>(
  method: "GET" | "POST", path: string, body?: object | Blob,
): Promise<T> {
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;
  if (method === "POST") {
    headers["X-Concurim-Token"] = token();
    if (body instanceof Blob) {
      payload = body;
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }
  const resp = await fetch(path, { method, headers, body: payload });
  const text = await resp.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* not JSON */ }
  if (!resp.ok) {
    const msg = (data as { error?: string } | null)?.error;
    throw new Error(msg ?? `request failed (HTTP ${resp.status})`);
  }
  return data as T;
}

export const getSession = () => call<SessionInfo>("GET", "api/session");
export const openSample = (id: string) =>
  call<unknown>("POST", `api/samples/${encodeURIComponent(id)}/open`);
export const uploadTrace = (file: Blob, name: string) =>
  call<unknown>("POST", `api/trace?name=${encodeURIComponent(name)}`, file);
export type Slot = "a" | "b";
export const uploadCompare = (slot: Slot, file: Blob, name: string) =>
  call<unknown>("POST", `api/compare/${slot}/trace?name=${encodeURIComponent(name)}`, file);
export const compareReplay = (slot: Slot) =>
  call<Replay>("GET", `api/compare/${slot}/replay`);
export const uploadWorkspace = (files: { path: string; data: string }[]) =>
  call<WorkspaceInfo>("POST", "api/workspaces", { files });
export const planRun = (req: RunRequest) =>
  call<RunPlan>("POST", "api/runs/plan", req);
export const startRun = (id: string) =>
  call<RunStatus>("POST", `api/runs/${id}/start`);
export const getRun = (id: string) =>
  call<RunStatus>("GET", `api/runs/${id}`);
export const cancelRun = (id: string) =>
  call<RunStatus>("POST", `api/runs/${id}/cancel`);
/** Load the latest flushed trace into the viewer. The run may still be going. */
export const openSnapshot = (id: string) =>
  call<RunStatus>("POST", `api/runs/${id}/snapshot`);

export const startExport = (req: ExportRequest) =>
  call<ExportStatus>("POST", "api/export", req);
export const getExport = (id: string) =>
  call<ExportStatus>("GET", `api/export/${id}`);
export const cancelExport = (id: string) =>
  call<ExportStatus>("POST", `api/export/${id}/cancel`);
/** Where a finished export is downloaded from. */
export const exportFileUrl = (id: string) => `api/export/${id}/file`;

export async function sampleSource(id: string): Promise<string> {
  const resp = await fetch(`api/samples/${encodeURIComponent(id)}/source`);
  if (!resp.ok) throw new Error(`no source (HTTP ${resp.status})`);
  return resp.text();
}

/** Base64 of a file's bytes (chunked: String.fromCharCode has arg limits). */
export async function toBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let out = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    out += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(out);
}
