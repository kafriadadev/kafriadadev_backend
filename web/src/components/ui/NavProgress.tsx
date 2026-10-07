"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Phase = "idle" | "loading" | "done";

/**
 * Page-load feedback, the way people already know it: a thin pitch-green bar
 * along the top edge that creeps forward while the next page is on its way
 * and completes when it arrives, and a busy state on the button-styled link
 * that was pressed (its icon becomes a turning ring; `a[data-button][aria-busy]` in
 * globals.css). It starts only after a short pause, so a fast page shows
 * nothing. Forms have their own: the SubmitButton.
 *
 * JavaScript only, deliberately. Next's loading.tsx would stream a fallback
 * that, with JavaScript off, never gives way to the page; without JavaScript
 * the browser's own indicator does this job.
 */
export function NavProgress({ label }: { label: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const pressed = useRef<HTMLAnchorElement | null>(null);
  const pathname = usePathname();
  const search = useSearchParams();

  const release = () => {
    pressed.current?.removeAttribute("aria-busy");
    pressed.current = null;
  };

  // The new page has arrived: finish the bar, then clear it.
  useEffect(() => {
    release();
    setPhase((p) => (p === "loading" ? "done" : p));
  }, [pathname, search]);

  useEffect(() => {
    if (phase !== "done") return;
    const t = setTimeout(() => setPhase("idle"), 400);
    return () => clearTimeout(t);
  }, [phase]);

  useEffect(() => {
    let start: ReturnType<typeof setTimeout> | undefined;
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a || a.target || a.hasAttribute("download")) return;
      const to = new URL(a.href, location.href);
      if (to.origin !== location.origin) return;
      if (to.pathname === location.pathname && to.search === location.search) return; // a hash, or this page
      if (/\.(pdf|png|csv|json)$|\/(csv|pdf|export)$/.test(to.pathname)) return; // a download, not a page
      clearTimeout(start);
      start = setTimeout(() => {
        if (a.hasAttribute("data-button")) {
          a.setAttribute("aria-busy", "true");
          pressed.current = a;
        }
        setPhase("loading");
      }, 120);
    };
    const reset = () => {
      clearTimeout(start);
      release();
      setPhase("idle");
    };
    document.addEventListener("click", onClick);
    addEventListener("pageshow", reset);
    return () => {
      document.removeEventListener("click", onClick);
      removeEventListener("pageshow", reset);
      clearTimeout(start);
    };
  }, []);

  // A page that never arrives must not leave the bar up for good.
  useEffect(() => {
    if (phase !== "loading") return;
    const t = setTimeout(() => {
      release();
      setPhase("idle");
    }, 20_000);
    return () => clearTimeout(t);
  }, [phase]);

  if (phase === "idle") return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[80] h-[3px] print:hidden" role="progressbar" aria-label={label} aria-busy={phase === "loading"}>
      <div className={phase === "loading" ? "nav-bar nav-bar--loading" : "nav-bar nav-bar--done"} />
    </div>
  );
}
