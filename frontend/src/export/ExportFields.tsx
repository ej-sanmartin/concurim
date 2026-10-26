import type { ExportCaps } from "../api/types";
import {
  clipSeconds, eventCount, formatSeconds, FORMATS, FPS, PACES, SIZES, VIEWS,
  type ExportForm,
} from "./options";

interface Props {
  form: ExportForm;
  caps: ExportCaps;
  total: number;
  /** The event shown in the viewer (1-based), for the range shortcuts. */
  current: number;
  onChange: (patch: Partial<ExportForm>) => void;
}

const num = (v: string) => (v === "" ? NaN : Number(v));

/** The option groups of the export dialog (pure form, no network). */
export function ExportFields({ form, caps, total, current, onChange }: Props) {
  const videoOff = !caps.ffmpeg;
  return (
    <div className="export-fields">
      <fieldset>
        <legend>Format</legend>
        <div className="choices" role="radiogroup" aria-label="Format">
          {FORMATS.map((f) => {
            const off = videoOff && f.id !== "png";
            return (
              <label key={f.id} data-disabled={off || undefined}
                title={off ? caps.problems.ffmpeg : f.note}>
                <input type="radio" name="format" value={f.id} disabled={off}
                  checked={form.format === f.id}
                  onChange={() => onChange({ format: f.id })} />
                <b>{f.label}</b> <small>{f.note}</small>
              </label>
            );
          })}
        </div>
      </fieldset>

      <fieldset>
        <legend>What to show</legend>
        <div className="choices" role="radiogroup" aria-label="View">
          {VIEWS.map((v) => (
            <label key={v.id}>
              <input type="radio" name="view" value={v.id}
                checked={form.view === v.id}
                onChange={() => onChange({ view: v.id })} />
              {v.label}
            </label>
          ))}
        </div>
        <div className="toggles">
          <label><input type="checkbox" checked={form.explanation}
            data-testid="export-explanation"
            onChange={(e) => onChange({ explanation: e.target.checked })} />
            Explanation card</label>
          <label><input type="checkbox" checked={form.timeline}
            data-testid="export-timeline"
            onChange={(e) => onChange({ timeline: e.target.checked })} />
            Timeline</label>
          <label><input type="checkbox" checked={form.footer}
            data-testid="export-footer"
            onChange={(e) => onChange({ footer: e.target.checked })} />
            Footer (name, events, hash)</label>
          <label><input type="checkbox" checked={form.watermark}
            data-testid="export-watermark"
            onChange={(e) => onChange({ watermark: e.target.checked })} />
            Watermark (logo and name)</label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Events</legend>
        <div className="range">
          <label>from <input type="number" min={1} max={total}
            data-testid="export-start" value={Number.isNaN(form.start) ? "" : form.start}
            onChange={(e) => onChange({ start: num(e.target.value) })} /></label>
          <label>to <input type="number" min={1} max={total}
            data-testid="export-end" value={Number.isNaN(form.end) ? "" : form.end}
            onChange={(e) => onChange({ end: num(e.target.value) })} /></label>
          <span className="muted">of {total}</span>
          <button type="button" className="link"
            onClick={() => onChange({ start: 1, end: total })}>
            Whole recording</button>
          <button type="button" className="link"
            onClick={() => onChange({ start: current, end: total })}>
            From event {current}</button>
        </div>
      </fieldset>

      <fieldset>
        <legend>Look and pace</legend>
        <div className="grid">
          <label>Size
            <select value={form.size} data-testid="export-size"
              onChange={(e) => onChange({ size: e.target.value })}>
              {SIZES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select></label>
          <label>Pace
            <select value={form.hold} data-testid="export-pace"
              onChange={(e) => onChange({ hold: Number(e.target.value) })}>
              {PACES.map((p) => <option key={p.hold} value={p.hold}>{p.label}</option>)}
            </select></label>
          <label>Frame rate
            <select value={form.fps}
              onChange={(e) => onChange({ fps: Number(e.target.value) })}>
              {FPS.map((f) => <option key={f} value={f}>{f} fps</option>)}
            </select></label>
          <label>Theme
            <select value={form.theme}
              onChange={(e) => onChange({ theme: e.target.value as ExportForm["theme"] })}>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select></label>
        </div>
        <label className="toggle-row">
          <input type="checkbox" checked={form.smooth} data-testid="export-smooth"
            onChange={(e) => onChange({ smooth: e.target.checked })} />
          Smooth motion <small>items glide between events (off: straight cuts)</small>
        </label>
      </fieldset>

      <p className="export-summary" data-testid="export-summary">
        {Number.isInteger(eventCount(form)) && eventCount(form) > 0
          ? `${eventCount(form)} events · about ${formatSeconds(clipSeconds(form))}`
          : "Choose a valid range of events."}
      </p>
    </div>
  );
}
