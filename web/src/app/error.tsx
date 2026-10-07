"use client";

import { Button } from "@/components/ui/Button";
import { PageState } from "@/components/ui/PageState";
import messages from "../../messages/en.json";

/**
 * PUB-05, something failed at our end. Says nothing caused by the reader was
 * the cause, and hands over a short reference (the error's digest, which the
 * server log carries) to read down the phone.
 */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = messages.errors;
  const reference = (error.digest ?? "").replace(/[^a-z0-9]/gi, "").slice(0, 6).toUpperCase() || undefined;
  return (
    <PageState
      wideArt
      // A prebuilt file: this is a client component, and the drawing code would ride in every page's bundle.
      art={<img src="/figures/iso/held-red.svg" alt="" className="h-auto w-full" />}
      title={t.serverTitle}
      reference={reference}
      referenceHelp={t.refHelp}
      action={<Button size="lg" block onClick={reset}>{t.retry}</Button>}
      secondary={<a href="/">{t.home}</a>}
    >
      {t.serverText}
    </PageState>
  );
}
