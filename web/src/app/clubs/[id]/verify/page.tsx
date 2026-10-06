import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconCheck, IconFileText, IconLock, IconRefresh, IconShieldCheck } from "@/components/icons";
import { RaisedFlag } from "@/components/illustrations";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { PageState } from "@/components/ui/PageState";
import { Pill, type Tone } from "@/components/ui/Pill";
import { Stepper } from "@/components/ui/Stepper";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getClubVerification, getMe, getPayment, type ClubVerification, type Payment } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { resubmitClubAction, startClubPaymentAction, uploadDocumentAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("clubVerify"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
type T = Awaited<ReturnType<typeof getTranslations<"clubVerify">>>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
const FILE_TONE: Record<string, Tone> = { ready: "good", uploaded: "check", pending: "check", unreadable: "bad" };

/**
 * Verify a club (CLB-04): the club's registration document or LGA letter, one
 * payment, an administrator's decision. The same payment path as VER-03 with
 * a different price and beneficiary. Every rule is the API's; this screen
 * shows the state it reports and forwards three actions.
 */
export default async function VerifyClubPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Search> }) {
  const t = await getTranslations("clubVerify");
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let v: ClubVerification;
  let kuid: string | null = null;
  try {
    [v, kuid] = await Promise.all([getClubVerification(token, id), getMe(token).then((m) => m.kuid)]);
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
  const ready = v.document === "ready";
  const price = formatNaira(v.price_kobo);
  const steps = t.raw("steps") as string[];
  const step = v.state === "under_review" || v.verified ? 2 : ready ? 1 : 0;
  const gets = t.raw("gets") as string[];

  return (
    <AthleteShell current="clubs" kuid={kuid}>
      <div className="mb-6">
        <Stepper steps={steps} current={step} label={t("title")} progressText={`${t("title")} · ${steps[step]}`} />
      </div>
      <PageHead back={{ href: base, label: t("back") }} eyebrow={t("eyebrow", { name: v.club_name })} title={t("title")} />

      <div className="mb-6 space-y-3 empty:hidden">
        {error ? <Notice signal="red" title={t("error")}><p>{error}</p></Notice> : null}
        {one(query.saved) ? <Notice signal="done" title={t("saved")}><p>{t("savedText")}</p></Notice> : null}
        {payment ? <PaymentNotice t={t} payment={payment} again={`${base}/verify?reference=${encodeURIComponent(payment.reference)}`} /> : null}
      </div>

      {v.verified ? (
        <Notice signal="done" title={t("verified")}><p>{t("verifiedText")}</p></Notice>
      ) : v.club_status !== "approved" ? (
        <Notice signal="var" title={t("waiting")}><p>{t("waitingText")}</p></Notice>
      ) : v.state === "under_review" ? (
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

          {v.state === "rejected" && v.reason ? (
            <Notice signal="yellow" title={t("rejected")} className="mt-6">
              <blockquote className="border-l-4 border-boot pl-3">{v.reason}</blockquote>
              <p><strong>{t("noSecondFee")}</strong> {t("covered")}</p>
            </Notice>
          ) : null}

          <h2 className="mt-10 text-lg uppercase">{v.state === "rejected" ? t("resend") : t("document")}</h2>
          <form action={uploadDocumentAction} encType="multipart/form-data" className="mt-3 space-y-4">
            <input type="hidden" name="club" value={id} />
            <div className={cn("rounded-card border-2 border-dashed p-4", ready ? "border-pitch" : "border-line-strong")}>
              <div className="flex items-start justify-between gap-3">
                <label htmlFor="document" className="flex items-center gap-2 font-bold"><IconFileText size={20} aria-hidden="true" />{t("document")}</label>
                <Pill tone={FILE_TONE[v.document ?? ""] ?? "neutral"} icon={ready ? <IconCheck size={16} aria-hidden="true" /> : undefined}>
                  {t(`file.${v.document && ["ready", "uploaded", "pending", "unreadable"].includes(v.document) ? v.document : "none"}`)}
                </Pill>
              </div>
              <p className="mt-1 text-xs text-muted">{t("documentHint")}</p>
              <input id="document" name="document" type="file" accept="image/jpeg,image/png,image/webp"
                className="mt-3 block w-full text-xs file:mr-3 file:min-h-12 file:cursor-pointer file:rounded-pill file:border-0 file:bg-surface-2 file:px-4 file:font-bold file:text-text" />
            </div>
            <SubmitButton variant="secondary" pendingLabel={t("uploading")}>{t("upload")}</SubmitButton>
            <p className="text-xs text-muted">{t("uploadNote")}</p>
          </form>

          <div className="mt-8">
            {v.state === "rejected" ? (
              <form action={resubmitClubAction} className="space-y-2">
                <input type="hidden" name="club" value={id} />
                <SubmitButton disabled={!ready} pendingLabel={t("resubmitting")}>{t("resubmit")}</SubmitButton>
              </form>
            ) : v.paid ? (
              <Notice signal="done" title={t("paid")} />
            ) : (
              <form action={startClubPaymentAction} className="space-y-2">
                <input type="hidden" name="club" value={id} />
                <SubmitButton disabled={!ready} pendingLabel={t("paying")} icon={<IconLock size={20} aria-hidden="true" />}>{t("pay", { price })}</SubmitButton>
                <p className="text-xs text-muted">{ready ? t("leave") : t("needDocument")}</p>
              </form>
            )}
          </div>
        </>
      )}
    </AthleteShell>
  );
}

function PaymentNotice({ t, payment, again }: { t: T; payment: Payment; again: string }) {
  if (payment.state === "confirmed") return <Notice signal="done" title={t("confirmed")}><p>{t("confirmedText", { amount: formatNaira(payment.amount_kobo) })}</p></Notice>;
  if (payment.state === "checking") {
    return (
      <Notice signal="var" title={t("checking")} action={<Button href={again} variant="secondary" icon={<IconRefresh size={20} aria-hidden="true" />}>{t("checkAgain")}</Button>}>
        <p>{t("checkingText")}</p>
      </Notice>
    );
  }
  if (payment.state === "review") return <Notice signal="flag" title={t("needsCheck")}><p>{t("needsCheckText")}</p></Notice>;
  return <Notice signal="red" title={t("failed")}><p>{t("failedText")}</p></Notice>;
}
