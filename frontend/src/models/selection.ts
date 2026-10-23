/** What the user clicked: a thread, a queue or a data item. */
export type Selection =
  | { kind: "thread" | "queue" | "object"; id: string }
  | null;
