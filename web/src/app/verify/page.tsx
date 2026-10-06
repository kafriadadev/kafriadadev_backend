import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import {
  IconArrowRight, IconCamera, IconCash, IconCheck, IconCreditCard, IconIdBadge2, IconShieldCheck, IconUser, IconVarScreen,
} from "@/components/icons";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { Pill, type Tone } from "@/components/ui/Pill";
import { Silhouette } from "@/components/ui/PlayerCard";
import { Stepper } from "@/components/ui/Stepper";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getMe, getVerification, type FileStatus, type Me, type Verification } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { resubmitAction, uploadAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("verify"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
type T = Awaited<ReturnType<typeof getTranslations<"verify">>>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
const when = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" }) : "";

/**
 * Verification, whichever step the athlete is on (VER-01, 02, 04, 05). It
 * reads the API's record and shows the matching screen; it never decides. The
 * state moves only when a payment settles or a reviewer decides. Every action
 * is a plain form; uploads are a multipart POST.
 */
export default async function VerifyPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("verify");
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  let v: Verification;
  try {
    [me, v] = await Promise.all([getMe(token), getVerification(token)]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    if (error instanceof ApiError && error.status === 404) {
      return (
        <AthleteShell current="verify" kuid={null}>
          <PageHead title={t("title")} />
          <Notice signal="flag" title={t("notAthlete")}><p>{t("notAthleteText")}</p></Notice>
        </AthleteShell>
      );
    }
    throw error;
  }

  const error = one(params.error);
  const saved = one(params.saved);
  const step = v.state === "under_review" || v.state === "approved" ? 2 : v.ready_to_pay ? 1 : 0;
  const steps = t.raw("steps") as string[];

  return (
    <AthleteShell current="verify" kuid={me.kuid}>
      <div className="mb-6">
        <Stepper steps={steps} current={step} label={t("eyebrow")} progressText={`${t("eyebrow")} · ${steps[step]}`} />
      </div>

      {error ? (
        <Notice signal="red" title={t("error")} className="mb-6"><p>{error}</p></Notice>
      ) : saved ? (
        <Notice signal="done" title={t("saved")} className="mb-6"><p>{t("savedText")}</p></Notice>
      ) : null}

      {v.state === "under_review" ? (
        <UnderReview t={t} v={v} me={me} />
      ) : v.state === "approved" ? (
        <Approved t={t} me={me} />
      ) : v.state === "escalated" ? (
        <Escalated t={t} v={v} />
      ) : v.state === "rejected" ? (
        <Rejected t={t} v={v} />
      ) : (
        <Start t={t} v={v} me={me} withdrawn={v.state === "revoked"} />
      )}
    </AthleteShell>
  );
}

const FILE_TONE: Record<string, Tone> = { ready: "good", uploaded: "check", pending: "check", unreadable: "bad" };

function FileStatusPill({ t, status }: { t: T; status: FileStatus }) {
  const key = status && ["ready", "uploaded", "pending", "unreadable"].includes(status) ? status : "none";
  return (
    <Pill tone={FILE_TONE[key] ?? "neutral"} icon={key === "ready" ? <IconCheck size={16} aria-hidden="true" /> : undefined}>
      {t(`file.${key}`)}
    </Pill>
  );
}

/** The two files: a native file input each, so it works on every phone. */
function UploadForm({ t, v }: { t: T; v: Verification }) {
  const box = (name: "photo" | "document", label: string, hint: string, icon: React.ReactNode, status: FileStatus, capture?: "user") => (
    <div className={cn("rounded-card border-2 border-dashed p-4", status === "ready" ? "border-pitch" : "border-line-strong")}>
      <div className="flex items-start justify-between gap-3">
        <label htmlFor={name} className="flex items-center gap-2 font-bold">{icon}{label}</label>
        <FileStatusPill t={t} status={status} />
      </div>
      <p className="mt-1 text-xs text-muted">{hint}</p>
      <input
        id={name}
        name={name}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture={capture}
        className="mt-3 block w-full text-xs file:mr-3 file:min-h-12 file:cursor-pointer file:rounded-pill file:border-0 file:bg-surface-2 file:px-4 file:font-bold file:text-text"
      />
    </div>
  );
  return (
    <form id="upload" action={uploadAction} encType="multipart/form-data" className="scroll-mt-24 space-y-4">
      {box("photo", t("photo"), t("photoHint"), <IconCamera size={20} aria-hidden="true" />, v.photo, "user")}
      {box("document", t("document"), t("documentHint"), <IconIdBadge2 size={20} aria-hidden="true" />, v.document)}
      <SubmitButton variant="secondary" pendingLabel={t("uploading")}>{t("upload")}</SubmitButton>
      <p className="text-xs text-muted">{t("uploadNote")}</p>
    </form>
  );
}

function Start({ t, v, me, withdrawn }: { t: T; v: Verification; me: Me; withdrawn: boolean }) {
  const price = formatNaira(v.price_kobo);
  const processing = [v.photo, v.document].some((s) => s === "uploaded" || s === "pending");
  const gets = t.raw("gets") as string[];
  return (
    <>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} />
      {withdrawn ? <Notice signal="whistle" title={t("withdrawn")} className="mb-6"><p>{t("withdrawnText")}</p></Notice> : null}

      {/* VER-01: what it gets you, the price once, then the two routes as equals. */}
      <section aria-labelledby="pitch" className="rounded-card bg-surface p-5">
        <h2 id="pitch" className="text-xl uppercase">{t("pitch")}</h2>
        <div className="mt-4 flex items-center justify-center gap-4" aria-hidden="true">
          <figure className="text-center text-xs text-muted">
            <div className="grid h-24 w-20 place-items-end overflow-hidden rounded-input bg-surface-2"><Silhouette className="h-20 w-16 text-muted" /></div>
            <figcaption className="mt-1 font-bold">{t("now")}</figcaption>
          </figure>
          <IconArrowRight className="text-muted" />
          <figure className="text-center text-xs">
            <div className="relative grid h-24 w-20 place-items-center rounded-input bg-pitch text-on-pitch">
              <IconUser size={40} />
              <IconShieldCheck size={22} className="absolute -right-2 -top-2 rounded-full bg-bg text-pitch-ink" />
            </div>
            <figcaption className="mt-1 font-bold">{t("after")}</figcaption>
          </figure>
        </div>
        <ul className="mt-4 space-y-2">
          {gets.map((g) => (
            <li key={g} className="flex items-start gap-2"><IconCheck size={20} className="mt-0.5 shrink-0 text-link" aria-hidden="true" />{g}</li>
          ))}
        </ul>
        <p className="mt-5">
          <span className="block whitespace-nowrap font-display text-4xl font-extrabold italic scoreboard-digits">{price}</span>
          <span className="text-muted">{t("price")}</span>
        </p>
      </section>

      <h2 className="mt-8 text-lg uppercase">{t("routesTitle")}</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col rounded-card border-2 border-line-strong p-4">
          <p className="flex items-center gap-2 font-bold"><IconCreditCard aria-hidden="true" />{t("card")}</p>
          <p className="mt-1 flex-1 text-muted">{t("cardText")}</p>
          <Button href="#upload" size="lg" block className="mt-4">{t("card")}</Button>
        </div>
        <div className="flex flex-col rounded-card border-2 border-line-strong p-4">
          <p className="flex items-center gap-2 font-bold"><IconCash aria-hidden="true" />{t("cash")}</p>
          <p className="mt-1 flex-1 text-muted">{t("cashText", { price, lga: me.lga_name ?? t("cashNoLga") })}</p>
        </div>
      </div>

      {/* VER-02 */}
      <h2 className="mt-10 text-lg uppercase">{t("uploadTitle")}</h2>
      <div className="mt-3">
        <UploadForm t={t} v={v} />
      </div>
      {processing ? (
        <p className="mt-4 text-muted">{t("processing")} <a href="/verify">{t("checkAgain")}</a></p>
      ) : null}
      <div className="mt-6">
        {v.ready_to_pay ? (
          <Button href="/pay" size="lg" block iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>{t("continue")}</Button>
        ) : (
          <p className="rounded-card bg-surface p-4 text-center text-muted">{t("needBoth")}</p>
        )}
      </div>
    </>
  );
}

/** VER-04: the match timeline. Waiting is the correct action. */
function UnderReview({ t, v, me }: { t: T; v: Verification; me: Me }) {
  const paid = v.paid_amount_kobo !== null ? formatNaira(v.paid_amount_kobo) : formatNaira(v.price_kobo);
  const items: { label: string; state: "done" | "now" | "todo" }[] = [
    { label: t("received"), state: "done" },
    { label: v.paid_at ? t("paidAt", { amount: paid, when: when(v.paid_at) }) : t("paid", { amount: paid }), state: "done" },
    { label: v.attempt > 1 ? `${t("checking")} · ${t("attempt", { n: v.attempt })}` : t("checking"), state: "now" },
    { label: t("live"), state: "todo" },
  ];
  return (
    <>
      <PageHead eyebrow={t("eyebrow")} title={t("reviewTitle")} />
      <Notice signal="var" title={t("reviewLead")}><p>{t("reviewWhen")}</p></Notice>
      <section aria-labelledby="timeline" className="mt-8">
        <h2 id="timeline" className="text-lg uppercase">{t("timeline")}</h2>
        <ol className="mt-4 space-y-0 border-l-2 border-line-strong pl-6">
          {items.map((it) => (
            <li key={it.label} aria-current={it.state === "now" ? "step" : undefined} className="relative pb-6 last:pb-0">
              <span
                className={cn(
                  "absolute left-[-2.3rem] top-0 grid size-7 place-items-center rounded-full border-2",
                  it.state === "done" ? "border-pitch bg-pitch text-on-pitch" : it.state === "now" ? "border-check bg-check-bg text-check" : "border-line-strong bg-bg",
                )}
                aria-hidden="true"
              >
                {it.state === "done" ? <IconCheck size={16} stroke={3} /> : it.state === "now" ? <IconVarScreen size={16} /> : null}
              </span>
              <span className={cn(it.state === "todo" ? "text-muted" : "font-bold")}>{it.label}</span>
            </li>
          ))}
        </ol>
      </section>
      <p className="mt-8 text-muted">{t("reviewNotify", { phone: me.phone })}</p>
    </>
  );
}

function Approved({ t, me }: { t: T; me: Me }) {
  return (
    <>
      <PageHead eyebrow={t("eyebrow")} title={t("approvedTitle")} />
      <Notice signal="done" title={t("approvedLead")}
        action={me.kuid ? <Button href={`/a/${encodeURIComponent(me.kuid)}`} iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>{t("seeProfile")}</Button> : undefined}>
        <p>{t("approvedText")}</p>
      </Notice>
    </>
  );
}

function Escalated({ t, v }: { t: T; v: Verification }) {
  return (
    <>
      <PageHead eyebrow={t("eyebrow")} title={t("escalatedTitle")} />
      <Notice signal="flag" title={t("escalatedLead")}>
        <p>{t("escalatedText")}</p>
        {v.reason ? (
          <>
            <p className="font-bold">{t("reviewerWrote")}</p>
            <blockquote className="border-l-4 border-line-strong pl-3 italic">{v.reason}</blockquote>
          </>
        ) : null}
      </Notice>
    </>
  );
}

/** VER-05: a correctable problem. "You do not pay again" in bold, and the attempts left. */
function Rejected({ t, v }: { t: T; v: Verification }) {
  const ready = v.photo === "ready" && v.document === "ready";
  return (
    <>
      <PageHead eyebrow={t("eyebrow")} title={t("rejectedTitle")} />
      <Notice signal="yellow" title={t("reason")}>
        <blockquote className="border-l-4 border-boot pl-3 text-md">{v.reason}</blockquote>
        <p>
          <strong>{t("noSecondFee")}</strong> {t("covered", { amount: formatNaira(v.paid_amount_kobo ?? v.price_kobo) })}{" "}
          {t("attemptsLeft", { count: v.attempts_left })}
        </p>
      </Notice>
      <h2 className="mt-8 text-lg uppercase">{t("replace")}</h2>
      <div className="mt-3"><UploadForm t={t} v={v} /></div>
      <form action={resubmitAction} className="mt-6 space-y-2">
        <SubmitButton disabled={!ready} pendingLabel={t("resubmitting")}>{t("resubmit")}</SubmitButton>
        {!ready ? <p className="text-xs text-muted">{t("resubmitNeed")}</p> : null}
      </form>
    </>
  );
}
