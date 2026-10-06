import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconQrcode, IconSearch } from "@/components/icons";
import { Field, Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { SubmitButton } from "@/components/ui/SubmitButton";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("find"))("title") };
}

type Search = Record<string, string | string[] | undefined>;

/**
 * PUB-03: a way in for someone whose camera will not scan, or whose card has a
 * damaged code. The result is /a/{kuid} with no signature, so the profile
 * shows without the "Issued by" pill.
 */
export default async function FindPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("find");
  const empty = Boolean((await searchParams).empty);

  async function find(formData: FormData) {
    "use server";
    const raw = String(formData.get("kuid") ?? "").trim().toUpperCase();
    // Tidy what a person actually types off a card. The API normalises too;
    // doing it here keeps the address bar clean.
    const cleaned = raw.replace(/[‐-―_\s]+/g, "-").replace(/-{2,}/g, "-");
    if (!cleaned) redirect("/find?empty=1");
    redirect(`/a/${encodeURIComponent(cleaned)}`);
  }

  return (
    <Page>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />
      <form action={find} className="space-y-5">
        <Field name="kuid" label={t("label")} hint={t("hint")} error={empty ? t("empty") : null}>
          {(a) => (
            <Input
              {...a}
              required
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder="KA-NG-JG-___-____-______"
              className="font-mono uppercase tracking-wide"
            />
          )}
        </Field>
        <SubmitButton pendingLabel={t("submit")} icon={<IconSearch size={20} aria-hidden="true" />}>
          {t("submit")}
        </SubmitButton>
      </form>
      <Notice signal="whistle" className="mt-8" title={<span className="inline-flex items-center gap-2"><IconQrcode size={20} aria-hidden="true" /> {t("scan")}</span>} />
    </Page>
  );
}
