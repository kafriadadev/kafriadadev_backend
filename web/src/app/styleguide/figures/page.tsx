import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Iso } from "@/components/iso/Iso";
import { PREVIEW } from "@/components/iso/preview";
import { styleguideEnabled } from "@/lib/styleguide";

export const metadata: Metadata = { title: "Figures", robots: { index: false } };
export const dynamic = "force-dynamic";

/** Every isometric figure in each state it is drawn in. Tap one to replay its motion. */
export default function Figures() {
  if (!styleguideEnabled()) notFound();
  return (
    <div className="mx-auto max-w-wide px-4 py-8 sm:px-6">
      <header className="mb-10">
        <p className="font-mono text-xs text-muted"><a href="/styleguide">/styleguide</a> / figures</p>
        <h1 className="mt-2">Figures</h1>
        <p className="mt-3 max-w-measure text-md text-muted">
          Isometric figures, drawn on the server from components/iso. Green means lit: live or done. Print
          versions: docs/design/print (node scripts/iso-export.mjs).
        </p>
      </header>
      <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(PREVIEW).map(([name, fig]) => (
          <li key={name} className="rounded-card border border-line p-4">
            <Iso fig={fig} name={name} />
            <p className="mt-2 font-mono text-xs text-muted">{name}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
