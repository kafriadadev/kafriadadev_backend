"use client";

import { useFormStatus } from "react-dom";

/**
 * A submit button that shows the form is working.
 *
 * Progressive enhancement only: with JavaScript off this is an ordinary submit
 * button and the browser's own loading indicator does the job. With it on, the
 * button locks (so a slow network cannot produce a double payment or a double
 * upload) and a full-screen notice says what is happening. It must sit inside
 * the form it submits.
 */
export function SubmitButton({
  children,
  className = "btn btn--primary btn--block",
  pending: pendingMessage = "Working…",
  detail,
  disabled,
  name,
  value,
}: {
  children: React.ReactNode;
  className?: string;
  /** Shown on the button and in the notice while the request is running. */
  pending?: string;
  /** A second line in the notice, for the slow ones. */
  detail?: string;
  disabled?: boolean;
  name?: string;
  value?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <>
      <button
        type="submit"
        className={className}
        disabled={disabled || pending}
        aria-busy={pending}
        name={name}
        value={value}
      >
        {pending ? (
          <>
            <span className="spinner" aria-hidden="true" />
            {pendingMessage}
          </>
        ) : (
          children
        )}
      </button>
      {pending ? (
        <div className="busy" role="status" aria-live="polite">
          <div className="busy__card">
            <span className="spinner spinner--lg" aria-hidden="true" />
            <p className="busy__title">{pendingMessage}</p>
            {detail ? <p className="busy__detail">{detail}</p> : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
