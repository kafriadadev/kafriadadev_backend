import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconLock } from "@/components/icons";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { ErrorSummary, Field, Fieldset, Input, PhoneInput, Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { PositionPicker } from "@/components/ui/PositionPicker";
import { KuidStrip } from "@/components/ui/Scoreboard";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getMyAthleteDetails, type AthleteDetails } from "@/lib/api";
import { GENDERS, LEVELS, NOT_APPLICABLE, PILOT_SPORT, POSITIONS, SIDES } from "@/lib/profile";
import { sessionToken } from "@/lib/session";
import { updateDetailsAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("details"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
const dob = (iso: string): string => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

/**
 * My details (ATH-02). What registration fixed (name, sex, date of birth,
 * nationality, sport, LGA, the ID itself) is shown locked and explained,
 * because eligibility is judged on it; a coordinator changes it. What changes
 * with time is edited here.
 */
export default async function DetailsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("details");
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let d: AthleteDetails;
  try {
    d = await getMyAthleteDetails(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    if (error instanceof ApiError && error.status === 404) {
      return (
        <AthleteShell current="me" kuid={null}>
          <PageHead title={t("title")} />
          <Notice signal="flag" title={t("noAthlete")}><p>{t("noAthleteText")}</p></Notice>
        </AthleteShell>
      );
    }
    throw error;
  }

  const error = one(params.error);
  const badField = one(params.field);
  const err = (name: string) => (badField === name ? error : null);
  const incomplete = !d.address_line || !d.height_cm || !d.emergency_name;
  const football = d.sport === PILOT_SPORT;
  const positions = [...(POSITIONS[d.sport] ?? []), ...(football ? [] : [NOT_APPLICABLE])];
  const positionLabels = (await getTranslations()).raw("footballPositions") as Record<string, string>;
  const fixed: [string, string][] = [
    [t("name"), d.full_name],
    [t("sex"), d.gender ? GENDERS[d.gender] ?? d.gender : "—"],
    [t("dob"), dob(d.date_of_birth)],
    [t("nationality"), d.nationality ?? "—"],
    [t("sport"), d.sport],
    [t("lga"), d.lga_name],
    ...(d.email ? ([[t("email"), d.email]] as [string, string][]) : []),
  ];

  return (
    <AthleteShell current="me" kuid={d.kuid}>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />

      <div className="mb-8 space-y-4 empty:hidden">
        {one(params.saved) ? <Notice signal="done" title={t("saved")}><p>{t("savedText")}</p></Notice> : null}
        {error ? <ErrorSummary title={t("error")} errors={[{ field: badField || "address_line", message: error }]} /> : null}
        {!error && !one(params.saved) && incomplete ? <Notice signal="yellow" title={t("incomplete")}><p>{t("incompleteText")}</p></Notice> : null}
      </div>

      <section aria-labelledby="fixed" className="mb-10 rounded-card bg-surface p-5">
        <h2 id="fixed" className="flex items-center gap-2 text-lg uppercase"><IconLock size={20} aria-hidden="true" />{t("fixed")}</h2>
        {d.kuid ? <KuidStrip kuid={d.kuid} className="mt-4" /> : null}
        <p className="mt-3 text-xs text-muted">{t("fixedText")}</p>
        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {fixed.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs font-bold uppercase tracking-[0.1em] text-muted">{label}</dt>
              <dd className="font-bold">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <form action={updateDetailsAction} noValidate className="space-y-12">
        {/* Football only in the pilot; an older record's other sport is kept as it is. */}
        <input type="hidden" name="secondary_sport" value={d.secondary_sport ?? ""} />

        <Fieldset legend={t("game")}>
          {football ? (
            <PositionPicker legend={t("position")} value={d.playing_position} error={err("playing_position")} labels={positionLabels} />
          ) : (
            <Field name="playing_position" label={t("positionOther", { sport: d.sport })} error={err("playing_position")}>
              {(a) => (
                <Select {...a} required defaultValue={d.playing_position ?? ""}>
                  <option value="">{t("choose")}</option>
                  {positions.map((p) => <option key={p} value={p}>{p}</option>)}
                </Select>
              )}
            </Field>
          )}
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="secondary_position" label={t("secondPosition")} optional optionalLabel={(await getTranslations("ui"))("optional")} error={err("secondary_position")}>
              {(a) => (
                <Select {...a} defaultValue={d.secondary_position ?? ""}>
                  <option value="">{t("none")}</option>
                  {positions.map((p) => <option key={p} value={p}>{p}</option>)}
                </Select>
              )}
            </Field>
            <Field name="dominant_side" label={t("side")} error={err("dominant_side")}>
              {(a) => (
                <Select {...a} required defaultValue={d.dominant_side ?? ""}>
                  <option value="">{t("choose")}</option>
                  {Object.entries(SIDES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="level_played" label={t("level")} error={err("level_played")}>
              {(a) => (
                <Select {...a} required defaultValue={d.level_played ?? ""}>
                  <option value="">{t("choose")}</option>
                  {Object.entries(LEVELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="years_experience" label={t("years")} error={err("years_experience")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={0} max={60} required defaultValue={d.years_experience ?? ""} />}
            </Field>
            <Field name="height_cm" label={t("height")} error={err("height_cm")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={120} max={230} required defaultValue={d.height_cm ?? ""} />}
            </Field>
            <Field name="weight_kg" label={t("weight")} error={err("weight_kg")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={35} max={200} required defaultValue={d.weight_kg ?? ""} />}
            </Field>
          </div>
        </Fieldset>

        <Fieldset legend={t("address")}>
          <Field name="address_line" label={t("addressLine")} hint={t("addressHint")} error={err("address_line")}>
            {(a) => <Input {...a} required autoComplete="street-address" defaultValue={d.address_line ?? ""} />}
          </Field>
          <Field name="town" label={t("town")} error={err("town")}>
            {(a) => <Input {...a} required autoComplete="address-level2" defaultValue={d.town ?? ""} />}
          </Field>
        </Fieldset>

        <Fieldset legend={t("emergency")}>
          <Field name="emergency_name" label={t("emergencyName")} error={err("emergency_name")}>
            {(a) => <Input {...a} required defaultValue={d.emergency_name ?? ""} />}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="emergency_relationship" label={t("emergencyRelationship")} error={err("emergency_relationship")}>
              {(a) => <Input {...a} required defaultValue={d.emergency_relationship ?? ""} />}
            </Field>
            <Field name="emergency_phone" label={t("emergencyPhone")} error={err("emergency_phone")}>
              {(a) => <PhoneInput {...a} required defaultValue={d.emergency_phone ?? ""} />}
            </Field>
          </div>
        </Fieldset>

        <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
      </form>
    </AthleteShell>
  );
}
