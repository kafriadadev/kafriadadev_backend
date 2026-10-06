import { IconArrowLeft } from "@/components/icons";
import { cn } from "@/lib/cn";

/** The content column: 640px for athlete and public flows, 1280px for admin. */
export function Page({ wide = false, className, children }: { wide?: boolean; className?: string; children: React.ReactNode }) {
  return <div className={cn("mx-auto w-full px-4 pb-16 pt-8 sm:px-6", wide ? "max-w-wide" : "max-w-measure", className)}>{children}</div>;
}

/** The top of a screen: where you are, what it is, and one line on what to do. */
export function PageHead({
  eyebrow,
  title,
  lede,
  back,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  lede?: React.ReactNode;
  back?: { href: string; label: string };
  className?: string;
}) {
  return (
    <header className={cn("mb-8", className)}>
      {back ? (
        <a href={back.href} className="mb-4 inline-flex min-h-12 items-center gap-2 font-bold no-underline">
          <IconArrowLeft size={20} aria-hidden="true" />
          {back.label}
        </a>
      ) : null}
      {eyebrow ? <p className="text-xs font-bold uppercase tracking-[0.16em] text-link">{eyebrow}</p> : null}
      <h1 className="mt-1 motion-rise">{title}</h1>
      {lede ? <p className="mt-3 text-md text-muted">{lede}</p> : null}
    </header>
  );
}
