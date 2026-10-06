"use client";

import { useFormStatus } from "react-dom";
import { buttonClass, type ButtonSize, type ButtonVariant } from "./Button";
import { Spinner } from "./Spinner";

/**
 * A submit button that says what is happening while the form is sent.
 *
 * With JavaScript off it is an ordinary submit button and the browser shows
 * its own progress. With it on, the button locks (no double payment, no double
 * upload) and the label changes, for example "Creating your ID…", beside the
 * spinner. It must sit inside the form it submits.
 */
export function SubmitButton({
  children,
  pendingLabel,
  variant = "primary",
  size = "lg",
  block = true,
  icon,
  disabled,
  name,
  value,
  className,
}: {
  children: React.ReactNode;
  /** Shown while the request runs. Say what is happening, not "Loading". */
  pendingLabel: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  icon?: React.ReactNode;
  disabled?: boolean;
  name?: string;
  value?: string;
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      name={name}
      value={value}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={buttonClass({ variant, size, block, className })}
    >
      {/* On a green button the arc takes the text colour, or it would vanish. */}
      {pending ? <Spinner size={26} className="-my-1 [--spinner-arc:currentColor]" /> : icon}
      <span aria-live="polite">{pending ? pendingLabel : children}</span>
    </button>
  );
}
