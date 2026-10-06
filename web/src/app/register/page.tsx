import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { IconCalendar, IconLock, IconMail, IconMapPin, IconPhone, IconUser } from "@/components/icons";
import { Checkbox, ErrorSummary, Field, Fieldset, Input, PhoneInput, Select } from "@/components/ui/Field";
import { FlowSteps } from "@/components/ui/FlowSteps";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { PositionPicker } from "@/components/ui/PositionPicker";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { listLgas } from "@/lib/api";
import {
  GENDERS, LEVELS, NATIONALITIES, NIGERIAN, NIGERIAN_STATES, NOT_APPLICABLE, PILOT_SPORT, POSITIONS, SIDES,
} from "@/lib/profile";
import { registerAthlete } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("register"))("title") };
}

// Always fresh: which LGAs are open changes as waves roll out.
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Registration (AUT-01). One plain form, three parts: You, Your game, Your
 * account. No JavaScript needed. A refusal comes back with the message, the
 * field to point at and every value typed, except the password.
 */
export default async function RegisterPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("register");
  const tu = await getTranslations("ui");
  const params = await searchParams;
  const error = one(params.error);
  const badField = one(params.field);
  const v = (key: string) => one(params[key]);
  const err = (name: string) => (badField === name ? error : null);

  let lgas: Awaited<ReturnType<typeof listLgas>> = [];
  let loadFailed = false;
  try {
    lgas = await listLgas();
  } catch {
    loadFailed = true;
  }
  const open = lgas.filter((l) => l.is_open);
  const closed = lgas.filter((l) => !l.is_open);
  const positionLabels = (await getTranslations()).raw("footballPositions") as Record<string, string>;
  const optional = tu("optional");

  return (
    <Page>
      <FlowSteps current={0} />
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />

      <div className="mb-8 space-y-4 empty:hidden">
        {error ? <ErrorSummary title={t("summary")} errors={[{ field: badField || "first_name", message: error }]} /> : null}
        {loadFailed ? (
          <Notice signal="red" title={t("unreachable")}><p>{t("unreachableText")}</p></Notice>
        ) : null}
      </div>

      <form action={registerAthlete} noValidate className="space-y-12">
        <input type="hidden" name="sport" value={PILOT_SPORT} />

        <Fieldset legend={`1. ${t("you")}`}>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="first_name" label={t("firstName")} hint={t("firstNameHint")} error={err("first_name")} icon={<IconUser size={18} />}>
              {(a) => <Input {...a} required autoComplete="given-name" defaultValue={v("first_name")} />}
            </Field>
            <Field name="surname" label={t("surname")} error={err("surname")}>
              {(a) => <Input {...a} required autoComplete="family-name" defaultValue={v("surname")} />}
            </Field>
          </div>
          <Field name="middle_name" label={t("middleName")} optional optionalLabel={optional} error={err("middle_name")}>
            {(a) => <Input {...a} autoComplete="additional-name" defaultValue={v("middle_name")} />}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="gender" label={t("sex")} hint={t("sexHint")} error={err("gender")}>
              {(a) => (
                <Select {...a} required defaultValue={v("gender")}>
                  <option value="">{t("choose")}</option>
                  {Object.entries(GENDERS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="date_of_birth" label={t("dob")} hint={t("dobHint")} error={err("date_of_birth")} icon={<IconCalendar size={18} />}>
              {(a) => <Input {...a} type="date" required defaultValue={v("date_of_birth")} />}
            </Field>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="nationality" label={t("nationality")} error={err("nationality")}>
              {(a) => (
                <Select {...a} required defaultValue={v("nationality") || NIGERIAN}>
                  {NATIONALITIES.map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              )}
            </Field>
            <Field name="state_of_origin" label={t("stateOfOrigin")} error={err("state_of_origin")}>
              {(a) => (
                <Select {...a} required defaultValue={v("state_of_origin")}>
                  <option value="">{t("chooseState")}</option>
                  {NIGERIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                  <option value={NOT_APPLICABLE}>{t("notNigerian")}</option>
                </Select>
              )}
            </Field>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="phone" label={t("phone")} hint={t("phoneHint")} error={err("phone")} icon={<IconPhone size={18} />}>
              {(a) => <PhoneInput {...a} required placeholder="0803 000 0000" defaultValue={v("phone")} />}
            </Field>
            <Field name="email" label={t("email")} hint={t("emailHint")} error={err("email")} icon={<IconMail size={18} />}>
              {(a) => <Input {...a} type="email" required autoComplete="email" defaultValue={v("email")} />}
            </Field>
          </div>
          <Field name="address_line" label={t("address")} hint={t("addressHint")} error={err("address_line")}>
            {(a) => <Input {...a} required autoComplete="street-address" defaultValue={v("address_line")} />}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="town" label={t("town")} error={err("town")}>
              {(a) => <Input {...a} required autoComplete="address-level2" defaultValue={v("town")} />}
            </Field>
            <Field name="lga_id" label={t("lga")} hint={t("lgaHint")} error={err("lga_id")} icon={<IconMapPin size={18} />}>
              {(a) => (
                <Select {...a} required defaultValue={v("lga_id")}>
                  <option value="">{t("chooseLga")}</option>
                  {open.length ? (
                    <optgroup label={t("lgaOpen")}>
                      {open.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </optgroup>
                  ) : null}
                  {/* Listed, not hidden, so someone can find their town and be told when it opens. */}
                  {closed.length ? (
                    <optgroup label={t("lgaClosed")}>
                      {closed.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </optgroup>
                  ) : null}
                </Select>
              )}
            </Field>
          </div>
          <div className="space-y-5 rounded-card bg-surface p-4">
            <p className="font-bold">{t("emergency")}</p>
            <Field name="emergency_name" label={t("emergencyName")} error={err("emergency_name")}>
              {(a) => <Input {...a} required defaultValue={v("emergency_name")} />}
            </Field>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field name="emergency_relationship" label={t("emergencyRelationship")} hint={t("emergencyRelationshipHint")} error={err("emergency_relationship")}>
                {(a) => <Input {...a} required defaultValue={v("emergency_relationship")} />}
              </Field>
              <Field name="emergency_phone" label={t("emergencyPhone")} error={err("emergency_phone")}>
                {(a) => <PhoneInput {...a} required defaultValue={v("emergency_phone")} />}
              </Field>
            </div>
          </div>
        </Fieldset>

        <Fieldset legend={`2. ${t("game")}`}>
          <PositionPicker legend={t("position")} value={v("playing_position")} error={err("playing_position")} labels={positionLabels} />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="secondary_position" label={t("secondPosition")} optional optionalLabel={optional} error={err("secondary_position")}>
              {(a) => (
                <Select {...a} defaultValue={v("secondary_position")}>
                  <option value="">{t("none")}</option>
                  {POSITIONS[PILOT_SPORT].map((p) => <option key={p} value={p}>{p}</option>)}
                </Select>
              )}
            </Field>
            <Field name="level_played" label={t("level")} error={err("level_played")}>
              {(a) => (
                <Select {...a} required defaultValue={v("level_played")}>
                  <option value="">{t("choose")}</option>
                  {Object.entries(LEVELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="dominant_side" label={t("side")} error={err("dominant_side")}>
              {(a) => (
                <Select {...a} required defaultValue={v("dominant_side")}>
                  <option value="">{t("choose")}</option>
                  {Object.entries(SIDES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="years_experience" label={t("years")} error={err("years_experience")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={0} max={60} required defaultValue={v("years_experience")} />}
            </Field>
            <Field name="height_cm" label={t("height")} error={err("height_cm")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={120} max={230} required defaultValue={v("height_cm")} />}
            </Field>
            <Field name="weight_kg" label={t("weight")} error={err("weight_kg")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={35} max={200} required defaultValue={v("weight_kg")} />}
            </Field>
          </div>
        </Fieldset>

        <Fieldset legend={`3. ${t("account")}`}>
          <Field name="password" label={t("password")} hint={t("passwordHint")} error={err("password")} icon={<IconLock size={18} />}>
            {(a) => <Input {...a} type="password" required minLength={10} autoComplete="new-password" />}
          </Field>
          <Checkbox name="accept_privacy_notice" value="yes" required error={err("accept_privacy_notice")}>
            {t.rich("consent", { privacy: (chunks) => <a href="/privacy">{chunks}</a> })}
          </Checkbox>
        </Fieldset>

        <div className="space-y-4">
          <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
          <p className="text-center text-muted">
            {t("haveAccount")} <a href="/sign-in" className="font-bold">{t("signIn")}</a>
          </p>
        </div>
      </form>
    </Page>
  );
}
