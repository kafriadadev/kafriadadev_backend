"use client";

import { useEffect, useState } from "react";
import { IconCheck, IconCopy } from "@/components/icons";

/**
 * Copies text on tap. Renders nothing until JavaScript has run, so a phone
 * without it never sees a button that does nothing.
 */
export function CopyButton({ text, label, doneLabel }: { text: string; label: string; doneLabel: string }) {
  const [ready, setReady] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => setReady(typeof navigator !== "undefined" && !!navigator.clipboard), []);
  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => setDone(false), 1800);
    return () => clearTimeout(t);
  }, [done]);
  if (!ready) return null;
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard.writeText(text).then(() => setDone(true), () => undefined)}
      className="inline-flex min-h-8 items-center gap-1 rounded-pill px-2 font-bold text-link hover:bg-surface-2"
    >
      {done ? <IconCheck size={16} aria-hidden="true" /> : <IconCopy size={16} aria-hidden="true" />}
      <span aria-live="polite">{done ? doneLabel : label}</span>
    </button>
  );
}
