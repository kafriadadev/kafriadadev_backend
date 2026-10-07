"use client";

import { useRef } from "react";

/**
 * The player card leans towards a finger or pointer, a few degrees at most,
 * and settles back when let go. Decoration only: without JavaScript, or with
 * reduced motion, the card simply lies flat.
 */
export function Tilt({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const lean = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(900px) rotateX(${(-y * 8).toFixed(2)}deg) rotateY(${(x * 10).toFixed(2)}deg)`;
  };
  const settle = () => {
    if (ref.current) ref.current.style.transform = "";
  };
  return (
    <div
      ref={ref}
      onPointerMove={lean}
      onPointerLeave={settle}
      onPointerUp={settle}
      onPointerCancel={settle}
      className={`transition-transform duration-[var(--dur-quick)] ease-kick [transform-style:preserve-3d] ${className ?? ""}`}
    >
      {children}
    </div>
  );
}
