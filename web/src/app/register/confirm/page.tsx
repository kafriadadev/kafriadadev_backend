import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconShieldCheck } from "@/components/icons";
import { CodeInput, Field } from "@/components/ui/Field";
import { FlowSteps } from "@/components/ui/FlowSteps";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { pending } from "@/lib/session";
import { confirmEmailAction, resendCodeAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("confirm"))("eyebrow") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Confirm your email (AUT-02). Reached straight after registering, or after
 * signing in to an account whose email was never confirmed. The KUID already
 * exists by now, so this screen reassures before it asks. One input, not six
 * boxes: six boxes need JavaScript.
 */
export default async function ConfirmEmailPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("confirm");
  const params = await searchParams;
  const error = one(params.error);
  const sent = one(params.sent);

  const waiting = await pending();
  if (!waiting) redirect("/sign-in");

  return (
    <Page>
      <FlowSteps current={1} />
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("sentTo", { email: waiting.email || t("yourEmail") })} />

      <div className="mb-6 flex gap-3 rounded-card bg-pitch p-4 text-on-pitch">
        <IconShieldCheck className="shrink-0" aria-hidden="true" />
        <div>
          <p className="font-bold">{t("safe")}</p>
          <p>{t("safeText")}</p>
        </div>
      </div>

      {error ? (
        <Notice signal="red" title={t("error")} className="mb-6"><p>{error}</p></Notice>
      ) : sent ? (
        <Notice signal="whistle" title={t("sent")} className="mb-6"><p>{t("sentText")}</p></Notice>
      ) : null}

      <form action={confirmEmailAction} noValidate className="space-y-5">
        <Field name="code" label={t("label")} hint={t("hint")}>
          {(a) => <CodeInput {...a} required placeholder="000000" />}
        </Field>
        <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
      </form>

      {/* The server enforces the wait between codes and says so. */}
      <form action={resendCodeAction} className="mt-4">
        <SubmitButton variant="secondary" size="md" pendingLabel={t("resendPending")}>{t("resend")}</SubmitButton>
      </form>

      <p className="mt-8 text-xs text-muted">{t("why")}</p>
    </Page>
  );
}
