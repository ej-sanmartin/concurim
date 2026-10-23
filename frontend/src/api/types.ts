// Shapes returned by the local Concurim server (viewer/api.py).

export type AutoLevel = "none" | "threads" | "queues";
export type Observability = "managed" | "queues" | "threads";

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
  samples: SampleInfo[];
  planned: { title: string; needs: string }[];
  interpreters: Interpreter[];
  cwd: string;
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
  exception: string | null;
  error: string | null;
  script: string;
}
