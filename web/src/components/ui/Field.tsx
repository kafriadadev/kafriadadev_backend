import { IconRedCard } from "@/components/icons";
import { cn } from "@/lib/cn";

/*
 * Form fields. Every one is a native control, so it works with JavaScript off.
 * An error is never colour alone: a red-card icon, a sentence saying how to
 * fix it, a red border and a thicker left edge. The field shakes once (CSS).
 */

const control =
  "block w-full min-h-12 rounded-input border-2 border-line-strong bg-bg px-3 text-base text-text " +
  "placeholder:text-muted transition-[border-color,box-shadow] duration-[var(--dur-quick)] ease-kick " +
  "focus:border-[var(--focus)] focus:outline-none focus:ring-2 focus:ring-[var(--focus)] " +
  "aria-[invalid=true]:border-danger aria-[invalid=true]:border-l-[6px] aria-[invalid=true]:motion-shake";

export function controlClass(className?: string) {
  return cn(control, className);
}

type FieldProps = {
  /** The control's id and name. */
  name: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: string | null;
  optional?: boolean;
  /** "(optional)" in the reader's language. */
  optionalLabel?: string;
  icon?: React.ReactNode;
  className?: string;
  /** Receives the ids to wire aria-describedby and aria-invalid. */
  children: (a11y: { id: string; name: string; "aria-describedby"?: string; "aria-invalid"?: true }) => React.ReactNode;
};

export function Field({ name, label, hint, error, optional, optionalLabel = "optional", icon, className, children }: FieldProps) {
  const hintId = hint ? `${name}-hint` : undefined;
  const errorId = error ? `${name}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={name} className="flex items-center gap-2 font-bold">
        {icon ? <span className="text-muted" aria-hidden="true">{icon}</span> : null}
        <span>{label}</span>
        {optional ? <span className="font-normal text-muted">({optionalLabel})</span> : null}
      </label>
      {hint ? <p id={hintId} className="text-xs text-muted">{hint}</p> : null}
      {children({ id: name, name, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {error ? (
        <p id={errorId} className="flex items-start gap-2 font-bold text-danger">
          <IconRedCard size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className, ...rest } = props;
  return <input className={controlClass(className)} {...rest} />;
}

export function Select({ className, children, ...rest }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={controlClass(cn("appearance-none bg-[length:20px] bg-[right_12px_center] bg-no-repeat pr-10", "bg-[image:var(--select-arrow)]", className))}
      {...rest}
    >
      {children}
    </select>
  );
}

export function Textarea({ className, ...rest }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={controlClass(cn("min-h-28 py-2", className))} {...rest} />;
}

/**
 * A Nigerian phone number. +234 is shown, not typed; the API accepts the
 * local form (0803…) and the international one.
 */
export function PhoneInput({ className, ...rest }: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">) {
  return (
    <div className="flex">
      <span
        className="inline-flex min-h-12 shrink-0 items-center whitespace-nowrap rounded-l-input border-2 border-r-0 border-line-strong bg-surface-2 px-3 font-mono text-text"
        aria-hidden="true"
      >
        +234
      </span>
      <input
        type="tel"
        inputMode="tel"
        autoComplete="tel-national"
        className={controlClass(cn("min-w-0 rounded-l-none font-mono tracking-wide", className))}
        {...rest}
      />
    </div>
  );
}

/**
 * A one-time code: one big field, not six boxes (which need JavaScript).
 * Phones offer the code from the message when autocomplete is one-time-code.
 */
export function CodeInput({ className, ...rest }: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type">) {
  return (
    <input
      type="text"
      inputMode="numeric"
      autoComplete="one-time-code"
      pattern="[0-9]*"
      maxLength={6}
      className={controlClass(
        cn("min-h-16 text-center font-mono text-3xl tracking-[0.5em] scoreboard-digits", className),
      )}
      {...rest}
    />
  );
}

/** A tick box with its sentence. The whole row is the target. */
export function Checkbox({
  name,
  children,
  error,
  ...rest
}: { name: string; children: React.ReactNode; error?: string | null } & Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "type" | "name" | "children"
>) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={name}
        className={cn(
          "flex min-h-12 cursor-pointer items-start gap-3 rounded-card border-2 p-3",
          error ? "border-danger border-l-[6px]" : "border-line",
        )}
      >
        <input
          type="checkbox"
          id={name}
          name={name}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${name}-error` : undefined}
          className="mt-0.5 size-6 shrink-0 accent-[var(--pitch-deep)]"
          {...rest}
        />
        <span>{children}</span>
      </label>
      {error ? (
        <p id={`${name}-error`} className="flex items-start gap-2 font-bold text-danger">
          <IconRedCard size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

/** Groups fields under a heading: "You", "Your game", "Your account". */
export function Fieldset({ legend, children, className }: { legend: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <fieldset className={cn("space-y-5 border-0 p-0", className)}>
      <legend className="mb-4 font-display text-xl font-extrabold uppercase italic">{legend}</legend>
      {children}
    </fieldset>
  );
}

/**
 * The form summary: at the top, listing every problem as a link to its field.
 * Plain anchors, so it works with JavaScript off. Give it focus on arrival
 * (autoFocus on a tabIndex -1 element is honoured without script).
 */
export function ErrorSummary({ title, errors }: { title: string; errors: { field: string; message: string }[] }) {
  if (!errors.length) return null;
  return (
    <div role="alert" tabIndex={-1} className="rounded-card border-2 border-danger border-l-[6px] bg-danger-bg p-4 text-text">
      <p className="flex items-center gap-2 font-bold text-danger">
        <IconRedCard size={20} aria-hidden="true" />
        {title}
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-6">
        {errors.map((e) => (
          <li key={e.field}>
            <a href={`#${e.field}`} className="text-danger underline">{e.message}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}
