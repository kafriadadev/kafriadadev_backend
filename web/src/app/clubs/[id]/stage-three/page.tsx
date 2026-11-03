import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconCheck, IconLock, IconShieldCheck } from "@/components/icons";
import { RaisedFlag } from "@/components/illustrations";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { PageState } from "@/components/ui/PageState";
import { Pill, type Tone } from "@/components/ui/Pill";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getClubStage3, getMe, getPayment, type ClubStage3, type Payment } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import {
  removePhotoAction,
  resubmitStage3Action,
  saveLinksAction,
  startStage3PaymentAction,
  uploadPhotoAction,
} from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("clubStage3"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
const PHOTO_TONE: Record<string, Tone> = { ready: "good", uploaded: "check", pending: "check", unreadable: "bad" };
const MAX_LINKS = 5;
const MAX_PHOTOS = 6;

/**
 * Club stage three (GDOC 5.10): the club's links and photos, one payment, an
 * administrator's decision. Every rule is the API's; this screen shows the state it
 * reports and forwards the actions.
 */
export default async function ClubStageThreePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Search> }) {
  const t = await getTranslations("clubStage3");
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let s: ClubStage3;
  let kuid: string | null = null;
  try {
    [s, kuid] = await Promise.all([getClubStage3(token, id), getMe(token).then((m) => m.kuid)]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <PageState art={<RaisedFlag />} title={t("title")} action={<Button href="/me" size="lg" block>{t("back")}</Button>}>
            {t("noAccess")}
          </PageState>
        );
      }
    }
    throw error;
  }

  const reference = one(query.reference);
  let payment: Payment | null = null;
  if (reference) {
    try {
      payment = await getPayment(token, reference);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) throw error;
    }
  }
  const base = `/clubs/${encodeURIComponent(id)}`;
  const error = one(query.error);
  const saved = one(query.saved);
  const price = formatNaira(s.price_kobo);
  const editable = s.stage === 2 && (s.state === "none" || s.state === "draft" || s.state === "rejected");
  const readyPhotos = s.photos.filter((p) => p.status === "ready").length;
  const canPay = s.links.length > 0 && readyPhotos > 0;
  const gets = t.raw("gets") as string[];
  const linkSlots = Array.from({ length: MAX_LINKS }, (_, i) => s.links[i] ?? "");

  return (
    <AthleteShell current="clubs" kuid={kuid}>
      <PageHead back={{ href: base, label: t("back") }} eyebrow={t("eyebrow", { name: s.club_name })} title={t("title")} />

      <div className="mb-6 space-y-3 empty:hidden">
        {error ? <Notice signal="red" title={t("error")}><p>{error}</p></Notice> : null}
        {saved ? <Notice signal="done" title={t(saved === "photo" ? "photoSaved" : "linksSaved")} /> : null}
        {payment ? (
          payment.state === "confirmed" ? <Notice signal="done" title={t("confirmed")}><p>{t("confirmedText")}</p></Notice>
          : payment.state === "failed" ? <Notice signal="red" title={t("failed")}><p>{t("failedText")}</p></Notice>
          : <Notice signal="var" title={t("checking")}><p>{t("checkingText")}</p></Notice>
        ) : null}
      </div>

      {s.stage === 3 ? (
        <Notice signal="done" title={t("done")}><p>{t("doneText")}</p></Notice>
      ) : s.stage < 2 ? (
        <Notice signal="var" title={t("needStage2")} action={<Button href={`${base}/verify`} variant="secondary">{t("toStage2")}</Button>}>
          <p>{t("needStage2Text")}</p>
        </Notice>
      ) : s.state === "under_review" ? (
        <Notice signal="var" title={t("review")}><p>{t("reviewText")}</p></Notice>
      ) : (
        <>
          <section aria-labelledby="pitch" className="rounded-card bg-surface p-5">
            <h2 id="pitch" className="flex items-center gap-2 text-xl uppercase"><IconShieldCheck aria-hidden="true" />{t("pitch")}</h2>
            <ul className="mt-4 space-y-2">
              {gets.map((g) => <li key={g} className="flex items-start gap-2"><IconCheck size={20} className="mt-0.5 shrink-0 text-link" aria-hidden="true" />{g}</li>)}
            </ul>
            <p className="mt-5">
              <span className="block whitespace-nowrap font-display text-4xl font-extrabold italic scoreboard-digits">{price}</span>
              <span className="text-muted">{t("price")}</span>
            </p>
          </section>

          {s.state === "rejected" && s.reason ? (
            <Notice signal="yellow" title={t("rejected")} className="mt-6">
              <blockquote className="border-l-4 border-boot pl-3">{s.reason}</blockquote>
              <p>{t("noSecondFee")}</p>
            </Notice>
          ) : null}

          <h2 className="mt-10 text-lg uppercase">{t("links")}</h2>
          <p className="mt-1 text-xs text-muted">{t("linksHint")}</p>
          <form action={saveLinksAction} className="mt-3 space-y-3">
            <input type="hidden" name="club" value={id} />
            {linkSlots.map((link, i) => (
              <Field key={i} name={`link_${i}`} label={t("link", { n: i + 1 })} optional={i > 0} optionalLabel={t("optional")}>
                {(a) => <Input {...a} name="links" type="url" inputMode="url" placeholder="https://" defaultValue={link} disabled={!editable} />}
              </Field>
            ))}
            {editable ? <SubmitButton variant="secondary" pendingLabel={t("saving")}>{t("saveLinks")}</SubmitButton> : null}
          </form>

          <h2 className="mt-10 text-lg uppercase">{t("photos")}</h2>
          <p className="mt-1 text-xs text-muted">{t("photosHint", { max: MAX_PHOTOS })}</p>
          {s.photos.length ? (
            <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {s.photos.map((p) => (
                <li key={p.media_id} className="rounded-card border-2 border-line-strong p-2">
                  {p.status === "ready" ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={`${base}/stage-three/photo/${p.media_id}`} alt={t("photoAlt")} className="aspect-[4/3] w-full rounded-input object-cover" loading="lazy" />
                  ) : (
                    <div className="grid aspect-[4/3] place-items-center rounded-input bg-surface-2 text-xs text-muted">{t(`file.${p.status}`)}</div>
                  )}
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <Pill tone={PHOTO_TONE[p.status] ?? "neutral"}>{t(`file.${p.status}`)}</Pill>
                    {editable ? (
                      <form action={removePhotoAction}>
                        <input type="hidden" name="club" value={id} />
                        <input type="hidden" name="media" value={p.media_id} />
                        <SubmitButton variant="ghost" size="sm" pendingLabel={t("removing")}>{t("remove")}</SubmitButton>
                      </form>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
          {editable && s.photos.length < MAX_PHOTOS ? (
            <form action={uploadPhotoAction} encType="multipart/form-data" className="mt-4 space-y-3">
              <input type="hidden" name="club" value={id} />
              <label htmlFor="photo" className="font-bold">{t("addPhoto")}</label>
              <input id="photo" name="photo" type="file" accept="image/jpeg,image/png,image/webp"
                className="block w-full text-xs file:mr-3 file:min-h-12 file:cursor-pointer file:rounded-pill file:border-0 file:bg-surface-2 file:px-4 file:font-bold file:text-text" />
              <SubmitButton variant="secondary" pendingLabel={t("uploading")}>{t("upload")}</SubmitButton>
            </form>
          ) : null}

          <div className="mt-10">
            {s.state === "rejected" ? (
              <form action={resubmitStage3Action} className="space-y-2">
                <input type="hidden" name="club" value={id} />
                <SubmitButton disabled={!canPay} pendingLabel={t("resubmitting")}>{t("resubmit")}</SubmitButton>
              </form>
            ) : s.paid ? (
              <Notice signal="done" title={t("paid")} />
            ) : (
              <form action={startStage3PaymentAction} className="space-y-2">
                <input type="hidden" name="club" value={id} />
                <SubmitButton disabled={!canPay} pendingLabel={t("paying")} icon={<IconLock size={20} aria-hidden="true" />}>{t("pay", { price })}</SubmitButton>
                <p className="text-xs text-muted">{canPay ? t("leave") : t("needBoth")}</p>
              </form>
            )}
          </div>
        </>
      )}
    </AthleteShell>
  );
}
