import { IconPosition, IconShieldCheck } from "@/components/icons";
import { Logo } from "@/components/brand/Logo";
import { cn } from "@/lib/cn";
import { positionUnit } from "@/lib/positions";
import { KuidStrip } from "./Scoreboard";

/*
 * The player card: the emotional centre of the product. One design, many
 * sizes. It is printed on --plate-* tokens, so it never inverts in dark mode
 * and a photo of the card always matches the card.
 *
 * Our own design: a pitch-green crown with chalk lines, a kit-red stripe, the
 * name set like the back of a shirt, the KUID in a scoreboard strip. It does
 * not imitate any game's or league's cards.
 */

export type PlayerCardData = {
  kuid: string;
  fullName: string;
  position: string | null;
  lgaName: string;
  stateName: string;
  year: number;
  verified: boolean;
  /** Same-origin URL of the approved photograph, if any. */
  photoSrc?: string | null;
};

export type PlayerCardLabels = {
  idLabel: string;
  verified: string;
  photoAlt: string;
  noPhoto: string;
};

/** Shown in place of a photograph. Deliberate, not broken; never explained. */
export function Silhouette({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 80 96" className={className} aria-hidden="true" focusable="false">
      <circle cx="40" cy="32" r="16" fill="currentColor" />
      <path d="M8 96c0-22 14-36 32-36s32 14 32 36z" fill="currentColor" />
      <path d="M30 60l10 10 10-10" fill="none" stroke="var(--plate-bg)" strokeWidth="3" strokeLinejoin="round" />
    </svg>
  );
}

function Crown({ year }: { year: number }) {
  return (
    <div className="relative overflow-hidden bg-plate-accent px-4 pb-10 pt-3 text-boot">
      {/* Chalk lines: a centre circle and halfway line across the crown. */}
      <svg viewBox="0 0 200 80" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 size-full opacity-35" aria-hidden="true">
        <path d="M0 60H200" stroke="var(--chalk)" strokeWidth="2" fill="none" />
        <circle cx="100" cy="60" r="34" stroke="var(--chalk)" strokeWidth="2" fill="none" />
      </svg>
      <div className="relative flex items-center justify-between gap-2">
        <Logo className="h-5 w-auto text-boot" />
        <span className="font-mono text-xs font-bold scoreboard-digits">{year}</span>
      </div>
    </div>
  );
}

function Photo({ data, labels, className }: { data: PlayerCardData; labels: PlayerCardLabels; className?: string }) {
  return (
    <div className={cn("overflow-hidden rounded-input bg-[color-mix(in_srgb,var(--plate-muted)_14%,var(--plate-bg))] ring-4 ring-plate-bg", className)}>
      {data.photoSrc ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={data.photoSrc} alt={labels.photoAlt} className="size-full object-cover" width={120} height={144} />
      ) : (
        <Silhouette className="mt-[12%] size-full text-[color-mix(in_srgb,var(--plate-muted)_55%,var(--plate-bg))]" />
      )}
    </div>
  );
}

function PositionLine({ data }: { data: PlayerCardData }) {
  const unit = positionUnit(data.position);
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-plate-muted">
      {unit ? <IconPosition position={unit} size={28} stroke={1.75} className="text-plate-ink" /> : null}
      {data.position ? <span className="font-bold text-plate-ink">{data.position}</span> : null}
      <span>
        {data.lgaName}, {data.stateName}
      </span>
    </p>
  );
}

function VerifiedMark({ label }: { label: string }) {
  return (
    <span className="inline-flex min-h-7 items-center gap-1.5 rounded-pill bg-plate-accent px-3 text-xs font-bold text-boot">
      <IconShieldCheck size={16} aria-hidden="true" />
      {label}
    </span>
  );
}

/**
 * sm: a roster row. md: the profile and ID-ready card. lg: the hero card.
 * The card adapts to its box (container query), not to the screen. A
 * container has no width of its own, so the card always fills its box.
 */
export function PlayerCard({
  data,
  labels,
  size = "md",
  className,
  as: As = "article",
  nameAs: Name = "h2",
}: {
  data: PlayerCardData;
  labels: PlayerCardLabels;
  size?: "sm" | "md" | "lg";
  className?: string;
  as?: "article" | "div";
  /** h1 where the card is the page (the public profile). */
  nameAs?: "h1" | "h2" | "p";
}) {
  if (size === "sm") {
    return (
      <As className={cn("flex items-center gap-3 rounded-card bg-plate-bg p-2 pr-3 text-plate-ink shadow-lift ring-1 ring-[color-mix(in_srgb,var(--plate-ink)_10%,transparent)]", className)}>
        <Photo data={data} labels={labels} className="h-16 w-14 shrink-0 ring-0" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-lg font-extrabold uppercase italic leading-tight">{data.fullName}</p>
          <p className="truncate text-xs text-plate-muted">
            {data.position ?? ""}{data.position ? " · " : ""}{data.lgaName}
          </p>
          <p className="mt-0.5 whitespace-nowrap font-mono text-xs scoreboard-digits">{data.kuid}</p>
        </div>
        {data.verified ? <IconShieldCheck size={24} className="shrink-0 text-pitch-ink" aria-label={labels.verified} role="img" /> : null}
      </As>
    );
  }

  const big = size === "lg";
  return (
    <As
      className={cn(
        "@container relative w-full overflow-hidden rounded-card bg-plate-bg text-plate-ink shadow-float",
        "ring-1 ring-[color-mix(in_srgb,var(--plate-ink)_10%,transparent)]",
        big ? "max-w-sm" : "max-w-xs",
        className,
      )}
    >
      <Crown year={data.year} />
      {/* The kit stripe. */}
      <span className="absolute inset-x-0 top-14 h-1.5 -skew-y-3 bg-kit-red" aria-hidden="true" />
      <div className="relative -mt-8 px-4 pb-4">
        <Photo data={data} labels={labels} className={cn("aspect-[5/6]", big ? "w-36" : "w-28")} />
        <Name className={cn("mt-3 font-display font-extrabold uppercase italic leading-[0.95] text-plate-ink", big ? "text-3xl" : "text-2xl")}>
          {data.fullName}
        </Name>
        <div className="mt-2 space-y-2">
          <PositionLine data={data} />
          {data.verified ? <VerifiedMark label={labels.verified} /> : null}
        </div>
        <KuidStrip kuid={data.kuid} label={labels.idLabel} plate className="mt-4" />
      </div>
    </As>
  );
}

/**
 * The printed card, front and back, at ID-1 size (85.6 × 54 mm). Same design
 * as on screen; the backend's PNG and PDF renderer must match it.
 */
export function PrintCard({
  data,
  labels,
  qrSrc,
  back,
}: {
  data: PlayerCardData;
  labels: PlayerCardLabels;
  qrSrc: string;
  back: { scan: string; scanHelp: string; issuedBy: string };
}) {
  const face = "relative h-[54mm] w-[85.6mm] overflow-hidden rounded-[3mm] bg-plate-bg text-plate-ink ring-1 ring-[color-mix(in_srgb,var(--plate-ink)_14%,transparent)] print:ring-[0.2mm]";
  return (
    <div className="flex flex-wrap gap-4 print:gap-[6mm]">
      <article aria-label={data.fullName} className={face}>
        <div className="absolute inset-y-0 left-0 w-[30mm] bg-plate-accent">
          <svg viewBox="0 0 30 54" className="absolute inset-0 size-full opacity-35" aria-hidden="true">
            <path d="M0 27H30" stroke="var(--chalk)" strokeWidth=".5" fill="none" />
            <circle cx="15" cy="27" r="9" stroke="var(--chalk)" strokeWidth=".5" fill="none" />
          </svg>
          <Photo data={data} labels={labels} className="absolute left-[4mm] top-[6mm] h-[27mm] w-[22mm]" />
          <span className="absolute bottom-[3mm] left-[4mm] font-mono text-[2.6mm] font-bold text-boot">{data.year}</span>
        </div>
        <span className="absolute left-[30mm] top-0 h-full w-[1.2mm] bg-kit-red" aria-hidden="true" />
        <div className="absolute inset-y-0 left-[33mm] right-[3mm] flex flex-col py-[3mm]">
          <Logo className="h-[4.5mm] w-auto self-start text-plate-ink" />
          <p className="mt-[3mm] font-display text-[5.2mm] font-extrabold uppercase italic leading-[0.95]">{data.fullName}</p>
          <p className="mt-[1.5mm] text-[2.6mm] leading-tight text-plate-muted">
            {data.position ? <b className="text-plate-ink">{data.position}</b> : null}
            {data.position ? " · " : ""}
            {data.lgaName}, {data.stateName}
          </p>
          {data.verified ? (
            <span className="mt-[1.5mm] inline-flex items-center gap-[1mm] self-start rounded-pill bg-plate-accent px-[2mm] py-[0.5mm] text-[2.4mm] font-bold text-boot">
              <IconShieldCheck size={10} aria-hidden="true" />
              {labels.verified}
            </span>
          ) : null}
          <div className="mt-auto rounded-[1mm] bg-plate-strip px-[2mm] py-[1mm] text-plate-strip-text">
            <p className="text-[1.8mm] uppercase tracking-[0.18em]">{labels.idLabel}</p>
            <p className="whitespace-nowrap font-mono text-[3mm] scoreboard-digits">{data.kuid}</p>
          </div>
        </div>
      </article>

      <article aria-label={back.scan} className={cn(face, "flex items-center gap-[4mm] p-[4mm]")}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={qrSrc} alt={back.scanHelp} width={160} height={160} className="size-[40mm] shrink-0" />
        <div className="flex h-full flex-col">
          <p className="font-display text-[4.6mm] font-extrabold uppercase italic leading-none">{back.scan}</p>
          <p className="mt-[2mm] text-[2.5mm] leading-snug text-plate-muted">{back.scanHelp}</p>
          <p className="mt-auto text-[2.3mm] font-bold leading-snug">{back.issuedBy}</p>
        </div>
      </article>
    </div>
  );
}
