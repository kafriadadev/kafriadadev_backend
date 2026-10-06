import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "md" | "lg";

const VARIANT: Record<ButtonVariant, string> = {
  // Logo green with boot text (6.48:1): reads like a kit.
  primary: "bg-pitch text-on-pitch hover:bg-[color-mix(in_srgb,var(--pitch)_88%,var(--boot))] active:bg-pitch-deep active:text-chalk",
  secondary: "border-2 border-line-strong bg-bg text-text hover:bg-surface active:bg-surface-2",
  ghost: "text-link underline-offset-4 hover:underline active:opacity-80",
  danger: "bg-[var(--card-red)] text-chalk hover:opacity-90 active:opacity-80",
};

const SIZE: Record<ButtonSize, string> = {
  md: "min-h-12 px-5 text-base",
  // 56px tall: the one primary action on a phone screen.
  lg: "min-h-14 px-7 text-md",
};

export function buttonClass({
  variant = "primary",
  size = "md",
  block = false,
  className,
}: { variant?: ButtonVariant; size?: ButtonSize; block?: boolean; className?: string } = {}) {
  return cn(
    "inline-flex select-none items-center justify-center gap-2 rounded-pill font-display font-extrabold uppercase italic tracking-wide no-underline",
    "transition-[transform,background-color,opacity] duration-[var(--dur-tap)] ease-kick active:scale-[.98]",
    "disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100",
    VARIANT[variant],
    variant === "ghost" ? "min-h-12 px-2 normal-case not-italic font-body font-bold tracking-normal" : SIZE[size],
    block && "w-full",
    className,
  );
}

type Common = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  icon?: React.ReactNode;
  iconAfter?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
};

/** A button, or a link that looks like one when given `href`. One primary per screen. */
export function Button({
  variant,
  size,
  block,
  icon,
  iconAfter,
  className,
  children,
  href,
  ...rest
}: Common &
  (
    | ({ href: string } & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "className" | "children">)
    | ({ href?: undefined } & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children">)
  )) {
  const cls = buttonClass({ variant, size, block, className });
  const body = (
    <>
      {icon}
      <span>{children}</span>
      {iconAfter}
    </>
  );
  if (href !== undefined) {
    return (
      <a href={href} className={cls} {...(rest as React.AnchorHTMLAttributes<HTMLAnchorElement>)}>
        {body}
      </a>
    );
  }
  const b = rest as React.ButtonHTMLAttributes<HTMLButtonElement>;
  return (
    <button type={b.type ?? "button"} className={cls} {...b}>
      {body}
    </button>
  );
}

/** A square button for a single icon. The label is always given and read aloud. */
export function IconButton({
  label,
  icon,
  href,
  className,
  ...rest
}: { label: string; icon: React.ReactNode; href?: string; className?: string } & Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  "className" | "children"
>) {
  const cls = cn(
    "inline-grid size-12 place-items-center rounded-pill text-text",
    "transition-[transform,background-color] duration-[var(--dur-tap)] ease-kick hover:bg-surface-2 active:scale-95",
    className,
  );
  if (href) {
    return (
      <a href={href} aria-label={label} title={label} className={cn(cls, "no-underline")}>
        {icon}
      </a>
    );
  }
  return (
    <button type={rest.type ?? "button"} aria-label={label} title={label} className={cls} {...rest}>
      {icon}
    </button>
  );
}
