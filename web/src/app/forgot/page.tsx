import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { IconLock, IconPhone } from "@/components/icons";
import { CodeInput, Field, Input, PhoneInput } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { resetPasswordAction, sendResetCodeAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("forgot"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Forgot password (AUT-05). Two steps on one address, each a plain POST. An
 * unknown phone gets the same answer as a known one. Step two ends every
 * other session.
 */
export default async function ForgotPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("forgot");
  const params = await searchParams;
  const error = one(params.error);
  const sent = one(params.sent);
  const phone = one(params.phone);

  return (
    <Page>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={sent ? undefined : t("lede")} />

      {error ? (
        <Notice signal="red" title={t("error")} className="mb-6"><p>{error}</p></Notice>
      ) : null}

      {!sent ? (
        <form action={sendResetCodeAction} noValidate className="space-y-5">
          <Field name="phone" label={t("phone")} icon={<IconPhone size={18} />}>
            {(a) => <PhoneInput {...a} required placeholder="0803 000 0000" defaultValue={phone} />}
          </Field>
          <SubmitButton pendingLabel={t("sendPending")}>{t("send")}</SubmitButton>
        </form>
      ) : (
        <>
          <Notice signal="whistle" title={t("sent")} className="mb-6"><p>{t("sentText")}</p></Notice>
          <form action={resetPasswordAction} noValidate className="space-y-5">
            <input type="hidden" name="phone" value={phone} />
            <Field name="code" label={t("code")}>
              {(a) => <CodeInput {...a} required placeholder="000000" />}
            </Field>
            <Field name="new_password" label={t("newPassword")} hint={t("newPasswordHint")} icon={<IconLock size={18} />}>
              {(a) => <Input {...a} type="password" required minLength={10} autoComplete="new-password" />}
            </Field>
            <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
            <p className="text-xs text-muted">{t("signedOut")}</p>
          </form>
        </>
      )}

      <p className="mt-6 text-muted">{t("remembered")} <a href="/sign-in" className="font-bold">{t("signIn")}</a></p>
    </Page>
  );
}
