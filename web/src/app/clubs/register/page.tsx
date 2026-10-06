import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ClubFields } from "@/components/ClubFields";
import { IconLock, IconMail, IconPhone, IconUser } from "@/components/icons";
import { Checkbox, ErrorSummary, Field, Fieldset, Input, PhoneInput, Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { listLgas } from "@/lib/api";
import { OFFICIAL_ROLES } from "@/lib/clubProfile";
import { signUpClubAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("clubSignup"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

/**
 * A club signs up (CLB-01). Public: the representative creates their account
 * and the club in one form. Once they confirm their email, the club goes to an
 * administrator for approval. Free; the badge is optional and comes later.
 */
export default async function ClubSignUpPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("clubSignup");
  const params = await searchParams;
  const get = (k: string): string => {
    const v = params[k];
    return Array.isArray(v) ? (v[0] ?? "") : (v ?? "");
  };
  const all = (k: string): string[] => {
    const v = params[k];
    return Array.isArray(v) ? v : v ? [v] : [];
  };
  const error = get("error");
  const badField = get("field");
  const duplicate = get("duplicate") === "1";
  const err = (name: string) => (badField === name ? error : null);

  let open: { id: string; name: string }[] = [];
  let loadFailed = false;
  try {
    open = (await listLgas()).filter((l) => l.is_open);
  } catch {
    loadFailed = true;
  }
  const steps = t.raw("steps") as string[];

  return (
    <Page>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />

      <section aria-labelledby="how" className="mb-8 rounded-card bg-surface p-5">
        <h2 id="how" className="text-lg uppercase">{t("how")}</h2>
        <ol className="mt-3 space-y-2">
          {steps.map((s, i) => (
            <li key={s} className="flex gap-3">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-pitch text-xs font-bold text-on-pitch" aria-hidden="true">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
        <p className="mt-4 text-xs text-muted">{t("price")}</p>
      </section>

      <div className="mb-8 space-y-4 empty:hidden">
        {error ? (
          duplicate ? (
            <Notice signal="yellow" title={t("duplicate")}><p>{error} {t("duplicateText")}</p></Notice>
          ) : (
            <ErrorSummary title={t("error")} errors={[{ field: badField || "name", message: error }]} />
          )
        ) : null}
        {loadFailed ? <Notice signal="red" title={t("unreachable")}><p>{t("unreachableText")}</p></Notice> : null}
      </div>

      <form action={signUpClubAction} noValidate className="space-y-12">
        <ClubFields values={{ get, all }} badField={badField} error={error} lgas={open} />

        <Fieldset legend={t("you")}>
          <p className="-mt-2 text-xs text-muted">{t("youHint")}</p>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="rep_first_name" label={t("firstName")} error={err("rep_first_name")} icon={<IconUser size={18} />}>
              {(a) => <Input {...a} required autoComplete="given-name" defaultValue={get("rep_first_name")} />}
            </Field>
            <Field name="rep_surname" label={t("surname")} error={err("rep_surname")}>
              {(a) => <Input {...a} required autoComplete="family-name" defaultValue={get("rep_surname")} />}
            </Field>
          </div>
          <Field name="rep_role" label={t("role")} error={err("rep_role")}>
            {(a) => (
              <Select {...a} required defaultValue={get("rep_role")}>
                <option value="">—</option>
                {OFFICIAL_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </Select>
            )}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="rep_phone" label={t("phone")} error={err("rep_phone")} icon={<IconPhone size={18} />}>
              {(a) => <PhoneInput {...a} required defaultValue={get("rep_phone")} />}
            </Field>
            <Field name="rep_email" label={t("email")} hint={t("emailHint")} error={err("rep_email")} icon={<IconMail size={18} />}>
              {(a) => <Input {...a} type="email" required autoComplete="email" defaultValue={get("rep_email")} />}
            </Field>
          </div>
          <Field name="password" label={t("password")} hint={t("passwordHint")} error={err("password")} icon={<IconLock size={18} />}>
            {(a) => <Input {...a} type="password" required minLength={10} autoComplete="new-password" />}
          </Field>
        </Fieldset>

        <div className="space-y-4">
          {duplicate ? <Checkbox name="confirm_duplicate">{t("duplicateBox")}</Checkbox> : null}
          <Checkbox name="accept_privacy_notice" value="yes" required error={err("accept_privacy_notice")}>
            {t.rich("consent", { privacy: (chunks) => <a href="/privacy">{chunks}</a> })}
          </Checkbox>
          <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
          <p className="text-center text-muted">{t("have")} <a href="/sign-in" className="font-bold">{t("signIn")}</a></p>
        </div>
      </form>
    </Page>
  );
}
