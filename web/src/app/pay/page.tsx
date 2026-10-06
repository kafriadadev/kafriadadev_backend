import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconArrowRight, IconCash, IconLock, IconRefresh } from "@/components/icons";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { Stepper } from "@/components/ui/Stepper";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getMe, getPayment, getPaymentQuote, getVerification, type Payment, type PaymentQuote } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { startPaymentAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("pay"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
type T = Awaited<ReturnType<typeof getTranslations<"pay">>>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/** After this long, "checking" stops being a few seconds and is worth saying so. */
const STILL_CHECKING_MS = 2 * 60 * 1000;

/**
 * Payment (VER-03): leaving for Paystack, and coming back. With no
 * `reference` it is the price and the button; Paystack returns the person
 * with `?reference=`, and then it reads our own record of that payment.
 *
 * This screen grants nothing. The API records only what Paystack's signed
 * webhook (or the reconciler) told it, so typing a return address proves
 * nothing. "Check again" is a plain link: no polling.
 */
export default async function PayPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("pay");
  const tv = await getTranslations("verify");
  const params = await searchParams;
  const reference = one(params.reference);
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let kuid: string | null = null;
  let body: React.ReactNode;
  try {
    kuid = (await getMe(token)).kuid;
    body = reference ? await returned(t, token, reference) : await start(t, token, one(params.error));
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 401) redirect("/sign-in?ended=1");
    throw caught;
  }
  const steps = tv.raw("steps") as string[];
  return (
    <AthleteShell current="verify" kuid={kuid}>
      <div className="mb-6">
        <Stepper steps={steps} current={1} label={tv("eyebrow")} progressText={`${tv("eyebrow")} · ${steps[1]}`} />
      </div>
      {body}
    </AthleteShell>
  );
}

async function start(t: T, token: string, error: string) {
  let quote: PaymentQuote | null = null;
  let problem = error;
  try {
    quote = await getPaymentQuote(token);
    // Nothing to pay for until there is something to review; the API would refuse anyway.
    const verification = await getVerification(token);
    if (!quote.already_paid && !verification.ready_to_pay) redirect("/verify");
  } catch (caught) {
    if (!(caught instanceof ApiError) || caught.status === 401) throw caught;
    problem = problem || caught.message;
  }

  return (
    <>
      <PageHead back={{ href: "/verify", label: t("back") }} eyebrow={t("eyebrow")} title={t("title")} />
      {problem ? <Notice signal="red" title={t("error")} className="mb-6"><p>{problem}</p></Notice> : null}
      {quote ? (
        <section aria-labelledby="due" className="overflow-hidden rounded-card border border-line">
          <div className="bg-scoreboard p-5 text-scoreboard-text">
            <h2 id="due" className="text-xs font-bold uppercase not-italic tracking-[0.14em] opacity-85">{t("amountDue")}</h2>
            <p className="mt-1 whitespace-nowrap font-display text-4xl font-extrabold italic scoreboard-digits">{formatNaira(quote.amount_kobo)}</p>
            <p className="mt-1 text-xs opacity-85">
              {t("for")} · <span className="whitespace-nowrap font-mono">{quote.kuid}</span>
            </p>
          </div>
          <div className="space-y-4 p-5">
            {quote.already_paid ? (
              <Notice signal="done" title={t("alreadyPaid")} />
            ) : (
              <form action={startPaymentAction} className="space-y-3">
                <SubmitButton pendingLabel={t("pending")} icon={<IconLock size={20} aria-hidden="true" />}>{t("submit")}</SubmitButton>
                <p className="text-xs text-muted">{t("leave")}</p>
              </form>
            )}
            <p className="flex items-center gap-2 text-muted">
              <IconCash size={20} aria-hidden="true" />
              <a href="/verify">{t("cash")}</a>
            </p>
          </div>
        </section>
      ) : null}
    </>
  );
}

async function returned(t: T, token: string, reference: string) {
  let payment: Payment;
  try {
    payment = await getPayment(token, reference);
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 404) {
      return (
        <>
          <PageHead eyebrow={t("eyebrow")} title={t("title")} />
          <Notice signal="flag" title={t("notFound")} action={<Button href="/pay" variant="secondary">{t("startAgain")}</Button>}>
            <p>{t("notFoundText")}</p>
          </Notice>
        </>
      );
    }
    throw caught;
  }
  const again = `/pay?reference=${encodeURIComponent(payment.reference)}`;
  const age = Date.now() - new Date(payment.created_at).getTime();
  const amount = formatNaira(payment.amount_kobo);
  const checkAgain = <Button href={again} variant="secondary" icon={<IconRefresh size={20} aria-hidden="true" />}>{t("checkAgain")}</Button>;

  return (
    <>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} />
      {payment.state === "confirmed" ? (
        <Notice signal="done" title={t("confirmed")}
          action={<Button href="/verify" iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>{t("seeVerification")}</Button>}>
          <p>{t("confirmedText", { amount })}</p>
        </Notice>
      ) : payment.state === "checking" ? (
        <Notice signal="var" title={t("checking")} action={checkAgain}>
          <p>{age > STILL_CHECKING_MS ? t("checkingLong") : t("checkingSoon")} {t("checkingSafe")}</p>
        </Notice>
      ) : payment.state === "review" ? (
        <Notice signal="flag" title={t("review")}><p>{t("reviewText")}</p></Notice>
      ) : (
        <Notice signal="red" title={t("failed")}
          action={<div className="flex flex-wrap gap-2"><Button href="/pay">{t("tryAgain")}</Button>{checkAgain}</div>}>
          <p>{t("failedText")}</p>
        </Notice>
      )}
      <p className="mt-4 font-mono text-xs text-muted">{payment.reference}</p>
    </>
  );
}
