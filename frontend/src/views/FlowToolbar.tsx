export const CATEGORY_LABEL: Record<string, string> = {
  producer: "Producers",
  consumer: "Consumers",
  stage: "Stages",
  other: "Other threads",
  queue: "Queues",
  lock: "Locks",
  item: "Items",
};

interface Props {
  categories: string[];
  hidden: Set<string>;
  canFocus: boolean;
  /** Whether any worker group is big enough to collapse. */
  canGroup: boolean;
  grouped: boolean;
  onGroup: () => void;
  onToggle: (category: string) => void;
  onFit: () => void;
  onReset: () => void;
  onFocus: () => void;
}

/** Layout tools: fit, reset, focus the selection, show/hide categories. */
export function FlowToolbar(p: Props) {
  return (
    <div className="flow-toolbar" role="toolbar" aria-label="Graph layout">
      <button onClick={p.onFit} data-testid="fit" title="Fit graph to view (f)">
        Fit
      </button>
      <button onClick={p.onReset} data-testid="reset-layout"
        title="Automatic layout: forget dragged positions">
        Reset layout
      </button>
      <button onClick={p.onFocus} disabled={!p.canFocus} data-testid="focus"
        title="Center on the selected thread, queue, lock or item">
        Focus selection
      </button>
      {p.canGroup && (
        <button onClick={p.onGroup} data-testid="group-toggle" aria-pressed={p.grouped}
          title="Collapse many similar workers into one node">
          {p.grouped ? "Expand workers" : "Group workers"}
        </button>
      )}
      <span className="sep" />
      {p.categories.map((c) => (
        <label key={c} className="chip" data-off={p.hidden.has(c) || undefined}>
          <input type="checkbox" checked={!p.hidden.has(c)}
            onChange={() => p.onToggle(c)} data-testid={`show-${c}`} />
          {CATEGORY_LABEL[c] ?? c}
        </label>
      ))}
    </div>
  );
}
