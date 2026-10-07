import type { GetServerSideProps } from "next";

import { PublicDocument, translator } from "@/components/PublicDocument";
import { IconCalendar, IconLock, IconMail, IconMapPin, IconPhone, IconUser } from "@/components/icons";
import { buttonClass } from "@/components/ui/Button";
import { Checkbox, ErrorSummary, Field, Fieldset, Input, PhoneInput, Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { PositionPicker } from "@/components/ui/PositionPicker";
import { RunRail } from "@/components/ui/RunRail";
import { Stepper } from "@/components/ui/Stepper";
import { isUnreachable, listLgas, type Lga } from "@/lib/api";
import {
  GENDERS, LEVELS, NATIONALITIES, NIGERIAN, NIGERIAN_STATES, NOT_APPLICABLE, PILOT_SPORT, POSITIONS, SIDES,
} from "@/lib/profile";
import messages from "../../messages/en.json";

/**
 * Registration (AUT-01). One plain form, three parts: You, Your game, Your
 * account. It ships no framework: the form posts to /forms/register, which runs
 * the registration action, and a refusal comes back with the message, the field
 * to point at and every value typed, except the password. One small script,
 * /enhance.js, groups phone numbers as they are typed and labels the button
 * while the form is sent; without it everything still works.
 */
export const config = { runtime: "nodejs", unstable_runtimeJS: false };

type Props = { params: Record<string, string>; lgas: Lga[]; loadFailed: boolean };

export const getServerSideProps: GetServerSideProps<Props> = async ({ query, res }) => {
  const params: Record<string, string> = {};
  for (const [key, value] of Object.entries(query)) {
    const v = Array.isArray(value) ? value[0] : value;
    if (typeof v === "string") params[key] = v;
  }
  let lgas: Lga[] = [];
  let loadFailed = false;
  try {
    // Always fresh: which LGAs are open changes as waves roll out.
    lgas = await listLgas();
  } catch (error) {
    if (!isUnreachable(error)) throw error;
    loadFailed = true;
  }
  res.setHeader("Cache-Control", "private, no-store");
  return { props: { params, lgas, loadFailed } };
};

export default function RegisterPage({ params, lgas, loadFailed }: Props) {
  const t = translator();
  const error = params.error ?? "";
  const badField = params.field ?? "";
  const v = (key: string) => params[key] ?? "";
  const err = (name: string) => (badField === name ? error : null);
  const open = lgas.filter((l) => l.is_open);
  const closed = lgas.filter((l) => !l.is_open);
  const steps = t.raw("flow.steps") as string[];
  const positionLabels: Record<string, string> = messages.footballPositions;
  const optional = t("ui.optional");

  return (
    <PublicDocument title={t("register.title")}>
    <Page>
      <div className="mb-8">
        <Stepper steps={steps} current={0} label={t("flow.label")} progressText={t("ui.stepOf", { current: 1, total: steps.length })} />
      </div>
      <PageHead eyebrow={t("register.eyebrow")} title={t("register.title")} lede={t("register.lede")} />

      <div className="mb-8 space-y-4 empty:hidden">
        {error ? <ErrorSummary title={t("register.summary")} errors={[{ field: badField || "first_name", message: error }]} /> : null}
        {loadFailed ? (
          <Notice signal="red" title={t("register.unreachable")}><p>{t("register.unreachableText")}</p></Notice>
        ) : null}
      </div>

      <form method="post" action="/forms/register" noValidate className="space-y-12">
        <input type="hidden" name="sport" value={PILOT_SPORT} />
        <RunRail parts={[
          { id: "part-0", label: t("register.you") },
          { id: "part-1", label: t("register.game") },
          { id: "part-2", label: t("register.account") },
        ]} />

        <Fieldset id="part-0" legend={`1. ${t("register.you")}`}>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="first_name" label={t("register.firstName")} hint={t("register.firstNameHint")} error={err("first_name")} icon={<IconUser size={18} />}>
              {(a) => <Input {...a} required autoComplete="given-name" defaultValue={v("first_name")} />}
            </Field>
            <Field name="surname" label={t("register.surname")} error={err("surname")}>
              {(a) => <Input {...a} required autoComplete="family-name" defaultValue={v("surname")} />}
            </Field>
          </div>
          <Field name="middle_name" label={t("register.middleName")} optional optionalLabel={optional} error={err("middle_name")}>
            {(a) => <Input {...a} autoComplete="additional-name" defaultValue={v("middle_name")} />}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="gender" label={t("register.sex")} hint={t("register.sexHint")} error={err("gender")}>
              {(a) => (
                <Select {...a} required defaultValue={v("gender")}>
                  <option value="">{t("register.choose")}</option>
                  {Object.entries(GENDERS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="date_of_birth" label={t("register.dob")} hint={t("register.dobHint")} error={err("date_of_birth")} icon={<IconCalendar size={18} />}>
              {(a) => <Input {...a} type="date" required defaultValue={v("date_of_birth")} />}
            </Field>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="nationality" label={t("register.nationality")} error={err("nationality")}>
              {(a) => (
                <Select {...a} required defaultValue={v("nationality") || NIGERIAN}>
                  {NATIONALITIES.map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              )}
            </Field>
            <Field name="state_of_origin" label={t("register.stateOfOrigin")} error={err("state_of_origin")}>
              {(a) => (
                <Select {...a} required defaultValue={v("state_of_origin")}>
                  <option value="">{t("register.chooseState")}</option>
                  {NIGERIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                  <option value={NOT_APPLICABLE}>{t("register.notNigerian")}</option>
                </Select>
              )}
            </Field>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="phone" label={t("register.phone")} hint={t("register.phoneHint")} error={err("phone")} icon={<IconPhone size={18} />}>
              {(a) => <PhoneInput {...a} required placeholder="0803 000 0000" defaultValue={v("phone")} />}
            </Field>
            <Field name="email" label={t("register.email")} hint={t("register.emailHint")} error={err("email")} icon={<IconMail size={18} />}>
              {(a) => <Input {...a} type="email" required autoComplete="email" defaultValue={v("email")} />}
            </Field>
          </div>
          <Field name="address_line" label={t("register.address")} hint={t("register.addressHint")} error={err("address_line")}>
            {(a) => <Input {...a} required autoComplete="street-address" defaultValue={v("address_line")} />}
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="town" label={t("register.town")} error={err("town")}>
              {(a) => <Input {...a} required autoComplete="address-level2" defaultValue={v("town")} />}
            </Field>
            <Field name="lga_id" label={t("register.lga")} hint={t("register.lgaHint")} error={err("lga_id")} icon={<IconMapPin size={18} />}>
              {(a) => (
                <Select {...a} required defaultValue={v("lga_id")}>
                  <option value="">{t("register.chooseLga")}</option>
                  {open.length ? (
                    <optgroup label={t("register.lgaOpen")}>
                      {open.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </optgroup>
                  ) : null}
                  {/* Listed, not hidden, so someone can find their town and be told when it opens. */}
                  {closed.length ? (
                    <optgroup label={t("register.lgaClosed")}>
                      {closed.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </optgroup>
                  ) : null}
                </Select>
              )}
            </Field>
          </div>
          <div className="space-y-5 rounded-card bg-surface p-4">
            <p className="font-bold">{t("register.emergency")}</p>
            <Field name="emergency_name" label={t("register.emergencyName")} error={err("emergency_name")}>
              {(a) => <Input {...a} required defaultValue={v("emergency_name")} />}
            </Field>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field name="emergency_relationship" label={t("register.emergencyRelationship")} hint={t("register.emergencyRelationshipHint")} error={err("emergency_relationship")}>
                {(a) => <Input {...a} required defaultValue={v("emergency_relationship")} />}
              </Field>
              <Field name="emergency_phone" label={t("register.emergencyPhone")} error={err("emergency_phone")}>
                {(a) => <PhoneInput {...a} required defaultValue={v("emergency_phone")} />}
              </Field>
            </div>
          </div>
        </Fieldset>

        <Fieldset id="part-1" legend={`2. ${t("register.game")}`}>
          <PositionPicker legend={t("register.position")} value={v("playing_position")} error={err("playing_position")} labels={positionLabels} />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="secondary_position" label={t("register.secondPosition")} optional optionalLabel={optional} error={err("secondary_position")}>
              {(a) => (
                <Select {...a} defaultValue={v("secondary_position")}>
                  <option value="">{t("register.none")}</option>
                  {POSITIONS[PILOT_SPORT].map((p) => <option key={p} value={p}>{p}</option>)}
                </Select>
              )}
            </Field>
            <Field name="level_played" label={t("register.level")} error={err("level_played")}>
              {(a) => (
                <Select {...a} required defaultValue={v("level_played")}>
                  <option value="">{t("register.choose")}</option>
                  {Object.entries(LEVELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="dominant_side" label={t("register.side")} error={err("dominant_side")}>
              {(a) => (
                <Select {...a} required defaultValue={v("dominant_side")}>
                  <option value="">{t("register.choose")}</option>
                  {Object.entries(SIDES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </Select>
              )}
            </Field>
            <Field name="years_experience" label={t("register.years")} error={err("years_experience")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={0} max={60} required defaultValue={v("years_experience")} />}
            </Field>
            <Field name="height_cm" label={t("register.height")} error={err("height_cm")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={120} max={230} required defaultValue={v("height_cm")} />}
            </Field>
            <Field name="weight_kg" label={t("register.weight")} error={err("weight_kg")}>
              {(a) => <Input {...a} type="number" inputMode="numeric" min={35} max={200} required defaultValue={v("weight_kg")} />}
            </Field>
          </div>
        </Fieldset>

        <Fieldset id="part-2" legend={`3. ${t("register.account")}`}>
          <Field name="password" label={t("register.password")} hint={t("register.passwordHint")} error={err("password")} icon={<IconLock size={18} />}>
            {(a) => <Input {...a} type="password" required minLength={10} autoComplete="new-password" />}
          </Field>
          <Checkbox name="accept_privacy_notice" value="yes" required error={err("accept_privacy_notice")}>
            {t.rich("register.consent", { privacy: (chunks) => <a href="/privacy">{chunks}</a> })}
          </Checkbox>
        </Fieldset>

        <div className="space-y-4">
          <button type="submit" data-pending={t("register.pending")} data-label={t("register.submit")} className={buttonClass({ size: "lg", block: true })}>
            <span aria-live="polite">{t("register.submit")}</span>
          </button>
          <p className="text-center text-muted">
            {t("register.haveAccount")} <a href="/sign-in" className="font-bold">{t("register.signIn")}</a>
          </p>
        </div>
      </form>
    </Page>
    <script src="/enhance.js" defer />
    </PublicDocument>
  );
}
