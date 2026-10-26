import type { ExportCaps, ExportRequest } from "../api/types";

export type Format = "mp4" | "webm" | "gif" | "png";
export type View = "animation" | "code" | "timeline" | "resources";

/** What the dialog edits; ``toRequest`` turns it into the server's shape. */
export interface ExportForm {
  format: Format;
  view: View;
  /** 1-based, inclusive: the same numbers as the viewer's event box. */
  start: number;
  end: number;
  size: string;
  fps: number;
  /** Seconds each event stays on screen. */
  hold: number;
  /** Glide between events instead of cutting. */
  smooth: boolean;
  explanation: boolean;
  timeline: boolean;
  footer: boolean;
  /** Logo and the name, in the top-left of the picture. */
  watermark: boolean;
  theme: "dark" | "light";
}

export const SMOOTH_MS = 400;
export const FORMATS: { id: Format; label: string; note: string }[] = [
  { id: "mp4", label: "MP4", note: "plays everywhere" },
  { id: "webm", label: "WebM", note: "smaller, for the web" },
  { id: "gif", label: "GIF", note: "short loops, no sound, large" },
  { id: "png", label: "PNG frames", note: "a .zip of images" },
];
export const VIEWS: { id: View; label: string }[] = [
  { id: "animation", label: "Animation" },
  { id: "code", label: "Animation + code" },
  { id: "resources", label: "Resources" },
  { id: "timeline", label: "Timeline" },
];
export const SIZES = [
  { id: "720p", label: "720p (1280 × 720)" },
  { id: "1080p", label: "1080p (1920 × 1080)" },
  { id: "square", label: "Square (1080 × 1080)" },
];
export const PACES = [
  { hold: 0.6, label: "Fast (0.6 s per event)" },
  { hold: 1.2, label: "Steady (1.2 s per event)" },
  { hold: 2.4, label: "Slow (2.4 s per event)" },
];
export const FPS = [24, 30, 60];

/** Sensible starting values for the recording that is open. */
export function defaultForm(
  view: View, total: number, caps: ExportCaps | null,
): ExportForm {
  return {
    format: caps && !caps.ffmpeg ? "png" : "mp4",
    view, start: 1, end: total, size: "720p", fps: 30, hold: 1.2,
    smooth: true, explanation: true, timeline: true, footer: true,
    watermark: true,
    theme: "dark",
  };
}

/** The request body for ``POST api/export``. */
export function toRequest(f: ExportForm): ExportRequest {
  return {
    format: f.format, view: f.view, start: f.start, end: f.end,
    size: f.size, fps: f.fps, hold: f.hold,
    motion_ms: f.smooth ? SMOOTH_MS : 0,
    overlays: [
      ...(f.explanation ? ["explanation"] : []),
      ...(f.timeline ? ["timeline"] : []),
    ],
    footer: f.footer, watermark: f.watermark, theme: f.theme,
  };
}

/** Number of events the clip shows. */
export const eventCount = (f: ExportForm): number => f.end - f.start + 1;

/** Length of the finished clip in seconds (PNG frames follow the same rule). */
export const clipSeconds = (f: ExportForm): number => eventCount(f) * f.hold;

/** A reason the form cannot be exported yet, or null. */
export function problem(
  f: ExportForm, total: number, caps: ExportCaps,
): string | null {
  if (!caps.browser) return caps.problems.browser ?? "No browser found.";
  const video = f.format !== "png";
  if (video && !caps.ffmpeg) return caps.problems.ffmpeg ?? "ffmpeg missing.";
  const whole = Number.isInteger(f.start) && Number.isInteger(f.end);
  if (!whole || f.start < 1 || f.end < f.start || f.end > total) {
    return `Choose events from 1 to ${total}, first before last.`;
  }
  return null;
}

/** "1:05" style length for the summary line. */
export function formatSeconds(s: number): string {
  const whole = Math.round(s);
  const m = Math.floor(whole / 60);
  return m ? `${m}:${String(whole % 60).padStart(2, "0")}` : `${whole} s`;
}
