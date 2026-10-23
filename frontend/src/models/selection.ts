/** What the user clicked: a thread/task, a queue/pool, a lock or an item. */
export type Selection =
  | { kind: "thread" | "queue" | "sync" | "object"; id: string }
  | null;
