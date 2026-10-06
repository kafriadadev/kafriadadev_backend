"use client";

import { useEffect } from "react";

/**
 * Confetti in green, red and white, once, for 1.2 seconds: the ID-ready
 * moment only. Skipped under reduced motion and when the phone asks to save
 * data; the library is fetched only when it will actually run.
 */
export function Confetti() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const conn = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    if (conn?.saveData) return;
    let cancelled = false;
    import("canvas-confetti").then(({ default: confetti }) => {
      if (cancelled) return;
      const css = getComputedStyle(document.documentElement);
      const colors = ["--pitch", "--kit-red", "--chalk"].map((v) => css.getPropertyValue(v).trim());
      const end = Date.now() + 1200;
      const frame = () => {
        confetti({ particleCount: 4, angle: 60, spread: 60, origin: { x: 0, y: 0.7 }, colors, disableForReducedMotion: true });
        confetti({ particleCount: 4, angle: 120, spread: 60, origin: { x: 1, y: 0.7 }, colors, disableForReducedMotion: true });
        if (Date.now() < end && !cancelled) requestAnimationFrame(frame);
      };
      frame();
    }, () => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}
