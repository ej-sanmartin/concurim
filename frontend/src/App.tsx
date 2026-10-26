import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { domAnimation, LazyMotion, MotionConfig } from "motion/react";
import { getSession } from "./api/client";
import type { SessionInfo } from "./api/types";
import { Compare } from "./compare/Compare";
import { Home } from "./home/Home";
import type { Replay } from "./models/replay";

// The graph libraries load only when a recording is opened, not on Home.
const Viewer = lazy(() => import("./Viewer").then((m) => ({ default: m.Viewer })));

type Theme = "dark" | "light";

/** A fixture replay for tests/dev: a relative path, never a URL. */
function fixtureUrl(): string | null {
  const wanted = new URLSearchParams(location.search).get("replay");
  return wanted && /^[\w./-]+$/.test(wanted) && !wanted.startsWith("/") ? wanted : null;
}

async function fetchReplay(url: string): Promise<Replay> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("concurim-theme") as Theme | null) ??
      (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"),
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("concurim-theme", theme);
  }, [theme]);
  return [theme, () => setTheme(theme === "dark" ? "light" : "dark")];
}

interface Shown { replay: Replay; label: string; generation: number }

/**
 * Home (drop a program or trace, examples) or Viewer (one recording).
 * A server that already has a trace opens straight into the viewer.
 */
export function App() {
  const [theme, toggleTheme] = useTheme();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const [view, setView] = useState<"home" | "viewer" | "compare">("home");
  const [error, setError] = useState<string | null>(null);

  const open = useCallback(async () => {
    const info = await getSession();
    const replay = await fetchReplay("api/replay");
    setSession(info);
    setShown({ replay, label: info.label ?? "trace", generation: info.generation });
    setView("viewer");
  }, []);

  useEffect(() => {
    const fixture = fixtureUrl();
    const boot = fixture
      ? fetchReplay(fixture).then((replay) => {
        setShown({ replay, label: "fixture", generation: 0 });
        setView("viewer");
      })
      : getSession().then((info) => {
        // Show Home only when there is nothing to open (no flash of Home).
        if (info.has_trace) return open();
        setSession(info);
        if (new URLSearchParams(location.search).has("compare")) setView("compare");
      });
    boot.catch((e) => setError(String(e)));
  }, [open]);

  const goHome = () => getSession().then(setSession).then(() => setView("home"));
  const fail = (e: unknown) => setError(String(e));

  let body;
  if (error) {
    body = <div className="splash error">Could not load: {error}</div>;
  } else if (view === "viewer" && shown) {
    body = shown.replay.events.length === 0
      ? (
        <div className="splash">
          <p>
            This trace contains no events: the program may not have used
            anything the chosen observability level can see.
          </p>
          {shown.replay.warnings[0] && (
            <p className="warning">{shown.replay.warnings[0]}</p>
          )}
          <button data-testid="home" onClick={() => goHome().catch(fail)}>
            Back to home
          </button>
        </div>
      )
      : <Viewer key={shown.generation} replay={shown.replay} label={shown.label}
        theme={theme} onToggleTheme={toggleTheme}
        onHome={() => goHome().catch(fail)}
        exportCaps={session?.export ?? null} />;
  } else if (view === "compare" && session) {
    body = <Compare session={session} onToggleTheme={toggleTheme}
      onHome={() => goHome().catch(fail)} />;
  } else if (session) {
    body = <Home session={session} onToggleTheme={toggleTheme}
      onCompare={() => setView("compare")}
      onOpenTrace={() => open().catch(fail)}
      onBack={shown ? () => setView("viewer") : null} />;
  } else {
    body = <div className="splash">Starting…</div>;
  }
  return (
    <LazyMotion features={domAnimation} strict>
      <MotionConfig reducedMotion="user">
        <Suspense fallback={<div className="splash">Loading viewer…</div>}>
          {body}
        </Suspense>
      </MotionConfig>
    </LazyMotion>
  );
}
