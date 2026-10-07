"use client";

import { useEffect, useRef } from "react";

import { formatNaira } from "@/lib/money";

const FORMAT = {
  int: (n: number) => Math.round(n).toLocaleString("en-GB"),
  naira: (kobo: number) => formatNaira(Math.round(kobo)),
};

/**
 * A number that counts up from zero when the page arrives. The server sends
 * the final figure, so without JavaScript, or with reduced motion, the number
 * is simply there. Never longer than a signature moment (560 ms).
 */
export function CountUp({ value, format = "int" }: { value: number; format?: keyof typeof FORMAT }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || value <= 0 || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const show = FORMAT[format];
    const start = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const p = Math.min((now - start) / 560, 1);
      el.textContent = show(value * (1 - (1 - p) ** 3));
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
      el.textContent = show(value);
    };
  }, [value, format]);
  return <span ref={ref}>{FORMAT[format](value)}</span>;
}
