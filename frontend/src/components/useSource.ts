import { useEffect, useState } from "react";

const cache = new Map<string, string>();

/**
 * Text of an embedded source file (``null`` while loading or if it is not
 * part of the trace). Files are fetched once and kept for the session.
 */
export function useSource(file: string | null, embedded: boolean): string | null {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (!file || !embedded) return setText(null);
    const hit = cache.get(file);
    if (hit !== undefined) return setText(hit);
    let alive = true;
    fetch(`api/source?path=${encodeURIComponent(file)}`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((t) => {
        cache.set(file, t);
        if (alive) setText(t);
      })
      .catch(() => alive && setText(null));
    return () => { alive = false; };
  }, [file, embedded]);
  return text;
}
