import type { GetServerSideProps } from "next";

import { PublicDocument, translator } from "@/components/PublicDocument";
import { IconLock, IconMail, IconUser } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { getMe } from "@/lib/api";
import { SESSION_COOKIE } from "@/lib/session-cookie";

/**
 * Sign in (AUT-04). One screen for every role; the role decides how long the
 * session lasts. A wrong phone and a wrong password get the same message,
 * which the API decides. Zero JavaScript: the form posts to /forms/sign-in,
 * which runs the sign-in action and redirects.
 */
export const config = { runtime: "nodejs", unstable_runtimeJS: false };

type Props = { error: string; phone: string; needEmail: boolean; reset: boolean; ended: boolean };

const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

export const getServerSideProps: GetServerSideProps<Props> = async ({ query, req, res }) => {
  const token = req.cookies[SESSION_COOKIE];
  if (token) {
    const me = await getMe(token).catch(() => null);
    if (me) return { redirect: { destination: "/me", permanent: false } };
  }
  res.setHeader("Cache-Control", "private, no-store");
  return {
    props: {
      error: one(query.error),
      phone: one(query.phone),
      needEmail: one(query.need_email) === "1",
      reset: Boolean(one(query.reset)),
      ended: Boolean(one(query.ended)),
    },
  };
};

export default function SignInPage({ error, phone, needEmail, reset, ended }: Props) {
  const t = translator();
  return (
    <PublicDocument title={t("signIn.title")}>
      <Page>
        <PageHead eyebrow={t("signIn.eyebrow")} title={t("signIn.title")} />

        <div className="mb-6 empty:hidden">
          {error ? (
            <Notice signal="red" title={t("signIn.error")}><p>{error}</p></Notice>
          ) : reset ? (
            <Notice signal="done" title={t("signIn.reset")}><p>{t("signIn.resetText")}</p></Notice>
          ) : ended ? (
            <Notice signal="whistle" title={t("signIn.ended")}><p>{t("signIn.endedText")}</p></Notice>
          ) : null}
        </div>

        <form method="post" action="/forms/sign-in" noValidate className="space-y-5">
          {/* One field for either: the API works out whether it is a phone or an email. */}
          <Field name="phone" label={t("signIn.phone")} hint={t("signIn.phoneHint")} icon={<IconUser size={18} />}>
            {(a) => <Input {...a} required type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder="0803 000 0000" defaultValue={phone} />}
          </Field>
          <Field name="password" label={t("signIn.password")} icon={<IconLock size={18} />}>
            {(a) => <Input {...a} type="password" required autoComplete="current-password" />}
          </Field>
          {needEmail ? (
            <Field name="email" label={t("signIn.email")} hint={t("signIn.emailHint")} icon={<IconMail size={18} />}>
              {(a) => <Input {...a} type="email" required autoComplete="email" />}
            </Field>
          ) : null}
          <Button type="submit" size="lg" block>{t("signIn.submit")}</Button>
        </form>

        <div className="mt-6 space-y-2">
          <p><a href="/forgot">{t("signIn.forgot")}</a></p>
          <p className="text-muted">{t("signIn.noAccount")} <a href="/register" className="font-bold">{t("signIn.register")}</a></p>
        </div>
      </Page>
    </PublicDocument>
  );
}
