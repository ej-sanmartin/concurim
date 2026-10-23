// Turning a drag-and-drop or file-picker result into a flat file list.

export interface PickedFile {
  /** Path relative to the dropped folder (or just the file name). */
  path: string;
  file: File;
}

export const MAX_FILES = 2000;
export const MAX_TOTAL_BYTES = 64 * 1024 * 1024;

/** Directories that are never part of "the program" and can be huge. */
const SKIP_DIRS = new Set([
  ".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".tox",
  ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea", ".vscode",
]);

export class DropError extends Error {}

/** Read every file under a dropped entry (directories are walked). */
async function walk(entry: FileSystemEntry, out: PickedFile[]): Promise<void> {
  if (out.length > MAX_FILES) throw new DropError(`more than ${MAX_FILES} files`);
  if (entry.isFile) {
    const file = await new Promise<File>((ok, fail) =>
      (entry as FileSystemFileEntry).file(ok, fail));
    out.push({ path: entry.fullPath.replace(/^\//, ""), file });
    return;
  }
  if (SKIP_DIRS.has(entry.name)) return;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((ok, fail) =>
      reader.readEntries(ok, fail));
    if (batch.length === 0) break;
    for (const child of batch) await walk(child, out);
  }
}

/** Drop the shared top-level folder name so ``main.py`` sits at the root. */
function stripCommonRoot(files: PickedFile[]): PickedFile[] {
  const roots = new Set(files.map((f) => f.path.split("/")[0]));
  const nested = files.every((f) => f.path.includes("/"));
  if (roots.size !== 1 || !nested) return files;
  return files.map((f) => ({ ...f, path: f.path.split("/").slice(1).join("/") }));
}

/**
 * Files from a drop event. Must be called synchronously from the handler:
 * the browser clears ``dataTransfer`` once the event returns.
 */
export function collectDrop(dt: DataTransfer): Promise<PickedFile[]> {
  const entries: FileSystemEntry[] = [];
  for (const item of Array.from(dt.items)) {
    const entry = item.kind === "file" ? item.webkitGetAsEntry() : null;
    if (entry) entries.push(entry);
  }
  return (async () => {
    const out: PickedFile[] = [];
    for (const e of entries) await walk(e, out);
    return finish(stripCommonRoot(out));
  })();
}

/** Files from an ``<input type=file>`` (folder pickers set relative paths). */
export function collectInput(list: FileList): PickedFile[] {
  const files = Array.from(list).map((file) => ({
    path: file.webkitRelativePath || file.name,
    file,
  }));
  const kept = files.filter(
    (f) => !f.path.split("/").some((part) => SKIP_DIRS.has(part)));
  return finish(stripCommonRoot(kept));
}

function finish(files: PickedFile[]): PickedFile[] {
  const total = files.reduce((n, f) => n + f.file.size, 0);
  if (files.length > MAX_FILES) throw new DropError(`more than ${MAX_FILES} files`);
  if (total > MAX_TOTAL_BYTES) throw new DropError("more than 64 MB of files");
  return files;
}
