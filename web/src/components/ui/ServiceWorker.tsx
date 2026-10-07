"use client";

import { useEffect } from "react";

/** Registers /sw.js once the page is idle. Without JavaScript the site simply works online. */
export function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
    const register = () => navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    if ("requestIdleCallback" in window) (window as Window & { requestIdleCallback: (cb: () => void) => void }).requestIdleCallback(register);
    else setTimeout(register, 2000);
  }, []);
  return null;
}
