// Types mirroring the document produced by concurim.replay.build_replay.

export type Tone = "info" | "ok" | "wait" | "warn" | "error";
export type ThreadStatus =
  | "running"
  | "waiting"
  | "working"
  | "suspended"
  | "finished"
  | "failed"
  | "cancelled";

export interface Source {
  file: string;
  line: number;
  function: string;
}

/** Where a worker was seen by the background line sampler (approximate). */
export interface LineSample {
  /** Index of the last event before the sample. */
  at: number;
  actor: string;
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
  task_id?: string;
  resource_id?: string;
  object_id?: string;
  operation_id?: string;
  caused_by?: string;
  source?: Source;
  metadata?: Record<string, string | number | boolean | null>;
}

/** The unit of execution an event belongs to: an asyncio task, else a thread. */
export const actorOf = (e: TraceEvent): string | undefined => e.task_id ?? e.thread_id;

export interface ThreadState {
  id: string;
  name: string;
  status: ThreadStatus;
  basis: "observed" | "inferred";
  waiting_on: { resource: string; op: string } | null;
  holding: string[];
  work: string | null;
  kind: "thread" | "task" | "process";
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
  /** An executor is drawn as its pending-task queue. */
  kind: "queue" | "executor";
  workers: number;
  running: number;
  shutdown: null | "graceful" | "immediate";
  blocked_puts: BlockedOp[];
  blocked_gets: BlockedOp[];
  joiners: string[];
}

export type SyncKind =
  | "lock" | "rlock" | "semaphore" | "event" | "condition" | "taskgroup";

/** A lock, semaphore, event, condition or task group. */
export interface SyncState {
  id: string;
  name: string;
  kind: SyncKind;
  capacity: number;
  /** Permits available (semaphores). */
  value: number;
  /** One entry per hold, as actor ids. */
  holders: string[];
  waiters: BlockedOp[];
  /** Event: the flag. */
  is_set: boolean;
  /** Condition: id of its associated lock, when that lock is recorded. */
  lock: string | null;
  /** Condition: signals not yet matched by a resumed waiter. */
  notified: number;
  /** Task group: the tasks created in it. */
  members: string[];
  /** Task group: member tasks not finished. */
  running: number;
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
    syncs?: Record<string, SyncState>;
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
  kind:
    | "wait_put" | "wait_get" | "wait_join" | "wait_lock" | "wait_event"
    | "wait_condition" | "wait_taskgroup" | "hold" | "work";
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
  /** First and last line of each function, per file (absent in old traces). */
  code_ranges?: Record<string, [number, number][]>;
  line_samples?: LineSample[];
  events: TraceEvent[];
  frames: Frame[];
  entities: {
    threads: Record<
      string,
      { id: string; name: string; kind: "thread" | "task" | "process"; first: number; last: number }
    >;
    queues: Record<
      string,
      { id: string; name: string; maxsize: number; kind: "queue" | "executor"; workers: number }
    >;
    syncs: Record<
      string,
      { id: string; name: string; kind: SyncKind; capacity: number; lock: string | null }
    >;
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
