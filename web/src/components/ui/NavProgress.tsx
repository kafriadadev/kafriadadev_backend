"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Spinner } from "./Spinner";

/**
 * The logo spinner while the next page is on its way. A link press shows it
 * after a short pause (a fast page never flashes it); the new page, or coming
 * back with the Back button, takes it away. Forms have their own: the
 * SubmitButton. Without JavaScript the browser's own loading indicator does
 * this job, and nothing here renders.
 */
export function NavProgress({ label }: { label: string }) {
  const [waiting, setWaiting] = useState(false);
  const pathname = usePathname();
  const search = useSearchParams();

  useEffect(() => setWaiting(false), [pathname, search]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a || a.target || a.hasAttribute("download")) return;
      const to = new URL(a.href, location.href);
      if (to.origin !== location.origin) return;
      if (to.pathname === location.pathname && to.search === location.search) return; // a hash, or this page
      if (/\.(pdf|png|csv|json)$|\/(csv|pdf|export)$/.test(to.pathname)) return; // a download, not a page
      clearTimeout(timer);
      timer = setTimeout(() => setWaiting(true), 150);
    };
    const reset = () => {
      clearTimeout(timer);
      setWaiting(false);
    };
    document.addEventListener("click", onClick);
    addEventListener("pageshow", reset);
    return () => {
      document.removeEventListener("click", onClick);
      removeEventListener("pageshow", reset);
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!waiting) return;
    // A page that never arrives must not leave the spinner up for good.
    const giveUp = setTimeout(() => setWaiting(false), 20_000);
    return () => clearTimeout(giveUp);
  }, [waiting]);

  if (!waiting) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-20 z-[70] flex justify-center motion-fade print:hidden">
      <span className="rounded-full bg-bg p-2 text-text shadow-float">
        <Spinner size={40} label={label} />
      </span>
    </div>
  );
}
