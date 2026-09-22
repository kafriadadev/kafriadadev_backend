"use client";

import { useEffect, useState } from "react";

/**
 * Ticks down the wait before another code can be asked for.
 *
 * With JavaScript off, ``seconds`` never reaches the browser as a live number
 * anyway — this renders its ``children`` (the real, always-clickable resend
 * form) on first paint and every server render, so a click before the timer
 * ends still works: the server enforces the wait and answers with its own
 * message either way. Only once mounted does this hide that form behind a
 * disabled placeholder and count down, swapping the real form back in at zero.
 */
export function ResendCountdown({
  seconds,
  children,
}: {
  seconds: number;
  children: React.ReactNode;
}) {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (!seconds || seconds <= 0) return;
    setRemaining(seconds);
    const id = setInterval(() => {
      setRemaining((r) => {
        if (r === null || r <= 1) {
          clearInterval(id);
          return null;
        }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [seconds]);

  if (remaining === null) return <>{children}</>;

  return (
    <p className="resend-wait" role="status" aria-live="polite">
      <button type="button" className="btn btn--ghost" disabled>
        Send another code &middot; {remaining}s
      </button>
    </p>
  );
}
