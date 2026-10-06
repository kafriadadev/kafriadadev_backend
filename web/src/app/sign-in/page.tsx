import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconLock, IconMail, IconUser } from "@/components/icons";
import { Field, Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { getMe } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { signInAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("signIn"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Sign in (AUT-04). One screen for every role; the role decides how long the
 * session lasts. A wrong phone and a wrong password get the same message,
 * which the API decides.
 */
export default async function SignInPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("signIn");
  const params = await searchParams;
  const error = one(params.error);
  const needEmail = one(params.need_email) === "1";

  const token = await sessionToken();
  if (token) {
    const me = await getMe(token).catch(() => null);
    if (me) redirect("/me");
  }

  return (
    <Page>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} />

      <div className="mb-6 empty:hidden">
        {error ? (
          <Notice signal="red" title={t("error")}><p>{error}</p></Notice>
        ) : one(params.reset) ? (
          <Notice signal="done" title={t("reset")}><p>{t("resetText")}</p></Notice>
        ) : one(params.ended) ? (
          <Notice signal="whistle" title={t("ended")}><p>{t("endedText")}</p></Notice>
        ) : null}
      </div>

      <form action={signInAction} noValidate className="space-y-5">
        {/* One field for either: the API works out whether it is a phone or an email. */}
        <Field name="phone" label={t("phone")} hint={t("phoneHint")} icon={<IconUser size={18} />}>
          {(a) => <Input {...a} required type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder="0803 000 0000" defaultValue={one(params.phone)} />}
        </Field>
        <Field name="password" label={t("password")} icon={<IconLock size={18} />}>
          {(a) => <Input {...a} type="password" required autoComplete="current-password" />}
        </Field>
        {needEmail ? (
          <Field name="email" label={t("email")} hint={t("emailHint")} icon={<IconMail size={18} />}>
            {(a) => <Input {...a} type="email" required autoComplete="email" />}
          </Field>
        ) : null}
        <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
      </form>

      <div className="mt-6 space-y-2">
        <p><a href="/forgot">{t("forgot")}</a></p>
        <p className="text-muted">{t("noAccount")} <a href="/register" className="font-bold">{t("register")}</a></p>
      </div>
    </Page>
  );
}
