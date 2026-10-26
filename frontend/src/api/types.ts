// Shapes returned by the local Concurim server (viewer/api.py).

export type AutoLevel = "none" | "threads" | "queues" | "sync" | "asyncio";
export type Observability = "managed" | Exclude<AutoLevel, "none">;

export interface SampleInfo {
  id: string;
  title: string;
  observability: Observability;
  summary: string;
  watch: string[];
}

export interface Interpreter {
  path: string;
  label: string;
  version: string | null;
  /** null when the version is not known until the program runs. */
  supported: boolean | null;
}

export interface SessionInfo {
  version: string;
  has_trace: boolean;
  label: string | null;
  generation: number;
  /** Labels of the two recordings loaded for comparison (null: empty). */
  compare: { a: string | null; b: string | null };
  samples: SampleInfo[];
  planned: { title: string; needs: string }[];
  interpreters: Interpreter[];
  cwd: string;
  export: ExportCaps;
}

/** What this machine can export, and why not when it cannot. */
export interface ExportCaps {
  browser: boolean;
  ffmpeg: boolean;
  problems: Record<string, string>;
  formats: string[];
  video_formats: string[];
  views: string[];
  overlays: string[];
  themes: string[];
  sizes: string[];
}

export interface ExportRequest {
  format: string;
  view: string;
  start: number;
  end: number;
  size: string;
  fps: number;
  hold: number;
  motion_ms: number;
  overlays: string[];
  footer: boolean;
  watermark: boolean;
  theme: string;
}

export interface ExportStatus {
  id: string;
  state: "running" | "done" | "failed" | "cancelled";
  done: number;
  total: number;
  error: string | null;
  /** Suggested name of the downloaded file. */
  filename: string;
}

export interface WorkspaceInfo {
  id: string;
  file_count: number;
  python_files: string[];
  entries: string[];
  suggested: string;
}

export interface RunRequest {
  workspace_id?: string;
  entry?: string;
  script_path?: string;
  args: string;
  interpreter: string;
  auto: AutoLevel;
  include_source: boolean;
  preview: boolean;
}

export interface RunPlan {
  id: string;
  interpreter: string;
  script: string;
  args: string[];
  cwd: string;
  auto: AutoLevel;
  include_source: boolean;
  preview: boolean;
  command: string;
}

export interface RunStatus {
  id: string;
  state: "running" | "finished" | "failed" | "cancelled" | "error";
  exit_code: number | null;
  output: string;
  output_truncated: boolean;
  trace_ready: boolean;
  /** A flushed trace exists while the run may still be going. */
  snapshot_ready?: boolean;
  exception: string | null;
  error: string | null;
  script: string;
}
