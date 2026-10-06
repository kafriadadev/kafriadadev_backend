import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconArrowRight, IconCheck, IconX } from "@/components/icons";
import { BigWhistle, RaisedFlag } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { CoordinatorShell } from "@/components/ui/CoordinatorShell";
import { Checkbox, Field, Textarea } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { PageState } from "@/components/ui/PageState";
import { KuidStrip } from "@/components/ui/Scoreboard";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getMe, getReviewCase, getReviewQueue, type Me, type QueueItem, type ReviewCase } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { decideAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("coordNav"))("queue") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
const stamp = (iso: string | null): string =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" }) : "";
function waiting(iso: string): string {
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
  return hours < 1 ? "<1h" : hours < 48 ? `${hours}h` : `${Math.floor(hours / 24)}d`;
}

/**
 * Review queue and decision (CRD-02). One case at a time, everything needed
 * on one screen: the photo and document large, the claimed details beside
 * them, Approve (after the check tick) and Reject (with the reason the athlete
 * will read). Plain form posts; whether a decision is allowed is the API's.
 */
export default async function ReviewPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("review");
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  const own = me.roles.find((r) => r.scope_kind === "lga")?.scope_id ?? "";
  const lga = one(params.lga) || own;
  if (!lga) {
    return <PageState art={<RaisedFlag />} title={t("noLga")}>{t("noLgaText")}</PageState>;
  }

  let queue: QueueItem[];
  try {
    queue = await getReviewQueue(token, lga);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    if (error instanceof ApiError && error.status === 403) {
      return <PageState art={<RaisedFlag />} title={t("noAccess")}>{t("noAccessText")}</PageState>;
    }
    throw error;
  }

  const error = one(params.error);
  const done = one(params.done);
  const index = Math.max(Number.parseInt(one(params.n) || "0", 10) || 0, 0);
  const current = queue[index];
  let c: ReviewCase | null = null;
  if (current) {
    try {
      c = await getReviewCase(token, lga, current.request_id);
    } catch (caught) {
      if (!(caught instanceof ApiError) || caught.status !== 404) throw caught;
    }
  }

  const banner = error ? (
    <Notice signal="red" title={t("error")} className="mb-6"><p>{error}</p></Notice>
  ) : done ? (
    <Notice signal="done" title={done === "approved" ? t("approved") : done === "escalated" ? t("escalated") : t("rejected")} className="mb-6">
      <p>{t("told")}</p>
    </Notice>
  ) : null;

  if (!current || !c) {
    return (
      <CoordinatorShell current="queue" lga={lga} token={token}>
        {banner}
        <PageState art={<BigWhistle />} title={queue.length ? t("end") : t("allCaught")}
          action={queue.length ? <Button href={`/review?lga=${encodeURIComponent(lga)}`} size="lg" block>{t("first")}</Button> : undefined}>
          {queue.length ? t("endText") : t("allCaughtText")}
        </PageState>
      </CoordinatorShell>
    );
  }

  const media = (kind: string) => `/review-media/${encodeURIComponent(lga)}/${encodeURIComponent(c!.request_id)}/${kind}`;
  const next = `/review?${new URLSearchParams({ lga, n: String(index + 1) })}`;
  const checklist = t.raw("checklist") as string[];
  const lede = [
    t("lede", { age: waiting(current.submitted_at) }),
    c.paid_kobo !== null ? t("paid", { amount: formatNaira(c.paid_kobo), when: stamp(c.paid_at) }) : null,
  ].filter(Boolean).join(" · ");

  return (
    <CoordinatorShell current="queue" lga={lga} token={token}>
      {banner}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHead eyebrow={t("eyebrow", { count: queue.length })} title={t("title", { n: index + 1, total: queue.length })} lede={lede} className="mb-4" />
        <Button href={next} variant="ghost" iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>{t("skip")}</Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <section aria-label={t("photo")} className="grid gap-3 sm:grid-cols-2">
          {(["photo", "document"] as const).map((kind) => (
            <figure key={kind} className="overflow-hidden rounded-card border border-line bg-surface">
              <figcaption className="px-3 py-2 text-xs font-bold uppercase tracking-[0.1em] text-muted">{t(kind)}</figcaption>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={media(kind)} alt={t(`${kind}Alt`)} className="aspect-[4/5] w-full bg-surface-2 object-contain" width={480} height={600} />
            </figure>
          ))}
        </section>

        <div className="space-y-5">
          <section aria-labelledby="check" className="rounded-card border-2 border-line-strong p-4">
            <h2 id="check" className="text-lg uppercase">{t("check")}</h2>
            <dl className="mt-3 space-y-3">
              <div><dt className="text-xs font-bold uppercase tracking-[0.1em] text-muted">{t("name")}</dt><dd className="font-display text-2xl font-extrabold uppercase italic">{c.full_name}</dd></div>
              <div><dt className="text-xs font-bold uppercase tracking-[0.1em] text-muted">{t("dob")}</dt><dd className="font-bold">{c.date_of_birth} · {t("age", { age: c.age })}</dd></div>
              <div><dt className="text-xs font-bold uppercase tracking-[0.1em] text-muted">{t("attempt")}</dt><dd className="font-bold">{t("attemptOf", { n: c.attempt })}</dd></div>
            </dl>
            <KuidStrip kuid={c.kuid} label={t("id")} className="mt-4" />
          </section>

          <form action={decideAction} className="space-y-3">
            <input type="hidden" name="lga" value={lga} />
            <input type="hidden" name="id" value={c.request_id} />
            <Checkbox name="checked" value="yes" required>
              <span className="block font-bold">{checklist.join(" · ")}</span>
            </Checkbox>
            <SubmitButton name="decision" value="approve" pendingLabel={t("approving")} icon={<IconCheck size={22} stroke={3} aria-hidden="true" />}>
              {t("approve")}
            </SubmitButton>
          </form>

          <form action={decideAction} className="space-y-3 rounded-card bg-danger-bg p-4">
            <input type="hidden" name="lga" value={lga} />
            <input type="hidden" name="id" value={c.request_id} />
            <Field name="reason" label={t("rejectLabel")} hint={t("rejectHint")}>
              {(a) => <Textarea {...a} maxLength={1000} required />}
            </Field>
            <SubmitButton name="decision" value="reject" variant="danger" pendingLabel={t("rejecting")} icon={<IconX size={22} stroke={3} aria-hidden="true" />}>
              {t("reject")}
            </SubmitButton>
          </form>
        </div>
      </div>
    </CoordinatorShell>
  );
}
