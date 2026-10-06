import { CopyButton } from "./CopyButton";

/** "7K2Q9X" -> "7K2·Q9X": groups of three, so it can be read down a phone. */
export function groupRef(code: string) {
  return code.replace(/[^A-Z0-9]/gi, "").toUpperCase().replace(/(.{3})(?=.)/g, "$1·");
}

/**
 * The reference code on every error. Text first (selectable with JavaScript
 * off); a copy button arrives with JavaScript.
 */
export function RefChip({ code, help, copyLabel = "Copy", copiedLabel = "Copied" }: { code: string; help?: string; copyLabel?: string; copiedLabel?: string }) {
  const grouped = groupRef(code);
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="inline-flex min-h-8 items-center rounded-pill bg-surface-2 px-3 font-mono text-xs text-text">
        <span className="mr-2 text-muted">REF</span>
        <span className="scoreboard-digits">{grouped}</span>
      </span>
      <CopyButton text={grouped.replace(/·/g, "")} label={copyLabel} doneLabel={copiedLabel} />
      {help ? <span className="text-muted">{help}</span> : null}
    </div>
  );
}
