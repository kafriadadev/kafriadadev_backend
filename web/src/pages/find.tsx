import type { GetServerSideProps } from "next";

import { PublicDocument, translator } from "@/components/PublicDocument";
import { IconQrcode, IconSearch } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { WithKuids } from "@/components/ui/Kuid";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";

/**
 * PUB-03: a way in for someone whose camera will not scan, or whose card has a
 * damaged code. A GET form, so it needs no JavaScript and no server action: an
 * ID in the query string is tidied and sent on to /a/{kuid}, with no signature,
 * so the profile shows without the "Issued by" pill.
 */
export const config = { runtime: "nodejs", unstable_runtimeJS: false };

type Props = { empty: boolean };

export const getServerSideProps: GetServerSideProps<Props> = async ({ query }) => {
  if (typeof query.kuid !== "string") return { props: { empty: false } };
  // Tidy what a person actually types off a card. The API normalises too;
  // doing it here keeps the address bar clean.
  const cleaned = query.kuid.trim().toUpperCase().replace(/[‐-―_\s]+/g, "-").replace(/-{2,}/g, "-");
  if (!cleaned) return { props: { empty: true } };
  return { redirect: { destination: `/a/${encodeURIComponent(cleaned)}`, permanent: false } };
};

export default function FindPage({ empty }: Props) {
  const t = translator();
  return (
    <PublicDocument title={t("find.title")}>
      <Page>
        <PageHead eyebrow={t("find.eyebrow")} title={t("find.title")} lede={t("find.lede")} />
        <form method="get" action="/find" className="space-y-5">
          <Field name="kuid" label={t("find.label")} hint={<WithKuids text={t("find.hint")} />} error={empty ? t("find.empty") : null}>
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
          <Button type="submit" size="lg" block icon={<IconSearch size={20} aria-hidden="true" />}>{t("find.submit")}</Button>
        </form>
        <Notice signal="whistle" className="mt-8" title={<span className="inline-flex items-center gap-2"><IconQrcode size={20} aria-hidden="true" /> {t("find.scan")}</span>} />
      </Page>
    </PublicDocument>
  );
}
