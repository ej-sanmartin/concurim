// Types mirroring the document produced by concurim.replay.build_replay.

export type Tone = "info" | "ok" | "wait" | "warn" | "error";
export type ThreadStatus =
  | "running"
  | "waiting"
  | "working"
  | "finished"
  | "failed";

export interface Source {
  file: string;
  line: number;
  function: string;
}

export interface TraceEvent {
  schema_version: number;
  event_id: string;
  event_type: string;
  timestamp_ns: number;
  sequence: number;
  process_id: number;
  thread_id?: string;
  resource_id?: string;
  object_id?: string;
  operation_id?: string;
  caused_by?: string;
  source?: Source;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface ThreadState {
  id: string;
  name: string;
  status: ThreadStatus;
  basis: "observed" | "inferred";
  waiting_on: { queue: string; op: string } | null;
  holding: string[];
  work: string | null;
}

export interface BlockedOp {
  thread: string;
  object?: string | null;
  op: string | null;
}

export interface QueueState {
  id: string;
  name: string;
  maxsize: number;
  /** Head of the queue (front first); at most 64 ids. */
  items: string[];
  /** True occupancy, even when ``items`` is truncated. */
  size: number;
  unfinished: number;
  shutdown: null | "graceful" | "immediate";
  blocked_puts: BlockedOp[];
  blocked_gets: BlockedOp[];
  joiners: string[];
}

export type ObjectPhase =
  | "new"
  | "putting"
  | "queued"
  | "held"
  | "released"
  | "discarded";

export interface ObjectState {
  id: string;
  type: string | null;
  preview: string | null;
  parent: string | null;
  phase: ObjectPhase;
  at: string | null;
}

export interface Frame {
  i: number;
  changes: {
    threads?: Record<string, ThreadState>;
    queues?: Record<string, QueueState>;
    objects?: Record<string, ObjectState>;
  };
  explanation: {
    title: string;
    text: string;
    tone: Tone;
    inferred: string[];
  };
  motion: { object: string; from: string | null; to: string | null } | null;
}

export interface Span {
  kind: "wait_put" | "wait_get" | "wait_join" | "work";
  thread: string | null;
  resource: string | null;
  object: string | null;
  operation: string;
  start: number;
  end: number;
  outcome: "completed" | "timeout" | "failed" | "open";
  name?: string | null;
}

export interface Replay {
  replay_version: number;
  metadata: Record<string, any>;
  source_paths: string[];
  events: TraceEvent[];
  frames: Frame[];
  entities: {
    threads: Record<string, { id: string; name: string; first: number; last: number }>;
    queues: Record<string, { id: string; name: string; maxsize: number }>;
    objects: Record<
      string,
      {
        id: string;
        type: string | null;
        preview: string | null;
        parent: string | null;
        journey: [number, ObjectPhase, string | null][];
      }
    >;
  };
  spans: Span[];
  occupancy: Record<string, [number, number, number][]>;
  summary: { event_count: number; duration_ns: number; by_type: Record<string, number> };
  warnings: string[];
}
