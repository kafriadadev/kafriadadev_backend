/*
 * Line illustrations for empty and error states, in the icon style (round
 * caps, one stroke weight). Draw what is missing, never a sad face. Each is
 * inline SVG, a few hundred bytes. Colour: currentColor plus one brand accent.
 */

type Props = { className?: string };

/**
 * `figure` names a fine-line version in public/figures/ that public/delight.js
 * may swap in on a capable device (layer 2); without it, this drawing stays.
 */
function Frame({ className, children, figure }: Props & { children: React.ReactNode; figure?: string }) {
  return (
    <svg
      data-figure={figure}
      viewBox="0 0 160 120"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M8 108H152" strokeOpacity=".35" />
      {children}
    </svg>
  );
}

/** No results: a goal with an empty net. */
export function EmptyNet({ className }: Props) {
  const mesh = [];
  for (let x = 40; x <= 120; x += 10) mesh.push(<path key={`v${x}`} d={`M${x} 30L${x + (x - 80) * 0.12} 104`} strokeWidth="1.25" strokeOpacity=".5" />);
  for (let y = 40; y <= 100; y += 10) mesh.push(<path key={`h${y}`} d={`M32 ${y}H128`} strokeWidth="1.25" strokeOpacity=".5" />);
  return (
    <Frame className={className} figure="net">
      {mesh}
      <path d="M30 108V26H130V108" strokeWidth="5" />
      <circle cx="146" cy="100" r="7" stroke="var(--chalk-line)" />
    </Frame>
  );
}

/** Not allowed here: the assistant referee's raised flag. */
export function RaisedFlag({ className }: Props) {
  return (
    <Frame className={className}>
      <path d="M62 108V18" strokeWidth="4" />
      <path d="M62 20H112V52H62" fill="var(--yellow-card)" />
      <path d="M62 20L112 52M112 20L62 52" stroke="var(--card-red)" strokeWidth="2" />
    </Frame>
  );
}

/** No players yet: an empty dugout bench. */
export function EmptyBench({ className }: Props) {
  return (
    <Frame className={className} figure="bench">
      <path d="M16 46Q80 10 144 46" />
      <path d="M24 42V108M136 42V108" />
      <path d="M30 80H130M30 80V96M130 80V96" />
      {[46, 72, 98, 124].map((x) => (
        <path key={x} d={`M${x - 10} 80V64H${x + 6}V80`} strokeWidth="2.25" strokeOpacity=".7" />
      ))}
    </Frame>
  );
}

/** No clubs yet: a bare kit rail. */
export function KitRail({ className }: Props) {
  return (
    <Frame className={className} figure="rail">
      <path d="M20 24H140M30 24V108M130 24V108" />
      {[54, 80, 106].map((x) => (
        <path key={x} d={`M${x} 24v8a5 5 0 1 1 -5 5`} strokeWidth="2.25" />
      ))}
      <path d="M68 60l-8 6 4 8 4-2V96h24V72l4 2 4-8-8-6c-2 4-6 6-12 6s-10-2-12-6z" strokeWidth="2.25" strokeOpacity=".35" strokeDasharray="4 4" />
    </Frame>
  );
}

/** Nothing recorded yet, or the system is unreachable: a dark scoreboard. */
export function UnpluggedScoreboard({ className }: Props) {
  return (
    <Frame className={className}>
      <rect x="28" y="18" width="104" height="58" rx="6" />
      <path d="M48 36v22M62 36v22M98 36v22M112 36v22" strokeOpacity=".3" strokeWidth="5" />
      <circle cx="80" cy="47" r="2.5" fill="currentColor" />
      <path d="M80 76V88c0 8 -14 6 -14 14v6" />
      <path d="M60 104h12" />
      <path d="M86 98l6 6M92 98l-6 6" stroke="var(--card-red)" />
    </Frame>
  );
}

/** Offline. */
export function NoSignal({ className }: Props) {
  return (
    <Frame className={className}>
      <path d="M80 92v12" strokeWidth="5" />
      <path d="M64 76a24 24 0 0 1 32 0" strokeOpacity=".4" />
      <path d="M50 62a44 44 0 0 1 60 0" strokeOpacity=".4" />
      <path d="M36 48a64 64 0 0 1 88 0" strokeOpacity=".4" />
      <path d="M40 20L120 104" stroke="var(--card-red)" strokeWidth="4" />
    </Frame>
  );
}

/** Signed out, or information: the whistle. */
export function BigWhistle({ className }: Props) {
  return (
    <Frame className={className}>
      <circle cx="66" cy="74" r="24" />
      <path d="M84 60l50-20v18l-38 15" />
      <circle cx="66" cy="74" r="5" fill="currentColor" />
      <path d="M40 30l8 10M66 20v14M92 30l-8 10" stroke="var(--chalk-line)" />
    </Frame>
  );
}

/** A card held up: yellow (wait, try again) or red (blocked, failed). */
export function HeldCard({ className, colour }: Props & { colour: "yellow" | "red" }) {
  return (
    <Frame className={className}>
      <rect x="62" y="12" width="44" height="64" rx="6" transform="rotate(10 84 44)" fill={colour === "yellow" ? "var(--yellow-card)" : "var(--card-red)"} />
      <path d="M58 108V86c0-8 4-12 10-12h4c4 0 6-4 8-8l4-8" />
    </Frame>
  );
}
