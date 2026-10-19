import { getTranslations } from "next-intl/server";

import { IconMail, IconMapPin, IconPhone, IconRedCard, IconShirtSport } from "@/components/icons";
import { Field, Fieldset, Input, PhoneInput, Select } from "@/components/ui/Field";
import type { Lga } from "@/lib/api";
import { AGE_GROUPS, CATEGORIES, CLUB_LEVELS, CLUB_TYPES, OFFICIAL_ROLES } from "@/lib/clubProfile";
import { PILOT_SPORT } from "@/lib/profile";

type Values = { get(key: string): string; all(key: string): string[] };

/**
 * The club's record as form fields: the same sections in sign-up, staff
 * registration and editing. Football only in the pilot. When editing, sport
 * and area are shown as fixed text, because a club that changed either would
 * be a different club. The sporting details (category, levels, age groups,
 * registration number, colours, website) belong to stage two and are shown
 * only when editing.
 */
export async function ClubFields({
  values,
  badField,
  error,
  lgas,
  fixed,
  stage2 = false,
}: {
  values: Values;
  badField: string;
  error: string;
  /** Every LGA in the state, open ones first. Omitted when editing. */
  lgas?: Lga[];
  /** When editing: the sport and area, not editable. */
  fixed?: { sport: string; lga_name: string };
  /** Show the stage-two sporting details. */
  stage2?: boolean;
}) {
  const t = await getTranslations("clubFields");
  const optional = (await getTranslations("ui"))("optional");
  const v = values.get;
  const err = (name: string) => (badField === name ? error : null);
  const chosenGroups = values.all("age_groups");
  const chosenLevels = values.all("levels");
  const open = (lgas ?? []).filter((l) => l.is_open);
  const closed = (lgas ?? []).filter((l) => !l.is_open);
  const Fixed = ({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) => (
    <div className="space-y-1.5">
      <p className="flex items-center gap-2 font-bold"><span className="text-muted" aria-hidden="true">{icon}</span>{label}</p>
      <p className="flex min-h-12 items-center rounded-input bg-surface-2 px-3">{value}</p>
    </div>
  );

  return (
    <div className="space-y-12">
      <Fieldset legend={t("club")}>
        {fixed ? null : <input type="hidden" name="sport" value={PILOT_SPORT} />}
        <Field name="name" label={t("name")} hint={t("nameHint")} error={err("name")} icon={<IconShirtSport size={18} />}>
          {(a) => <Input {...a} required defaultValue={v("name")} />}
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field name="short_name" label={t("shortName")} hint={t("shortNameHint")} error={err("short_name")}>
            {(a) => <Input {...a} required maxLength={20} defaultValue={v("short_name")} />}
          </Field>
          <Field name="year_founded" label={t("founded")} error={err("year_founded")}>
            {(a) => <Input {...a} type="number" inputMode="numeric" min={1900} required defaultValue={v("year_founded")} />}
          </Field>
          <Field name="type" label={t("type")} error={err("type")}>
            {(a) => (
              <Select {...a} required defaultValue={v("type")}>
                <option value="">{t("choose")}</option>
                {Object.entries(CLUB_TYPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </Select>
            )}
          </Field>
          {fixed ? <Fixed label={t("sport")} value={fixed.sport} icon={<IconShirtSport size={18} />} /> : <Fixed label={t("sport")} value={PILOT_SPORT} icon={<IconShirtSport size={18} />} />}
        </div>
      </Fieldset>

      <Fieldset legend={t("ground")}>
        <Field name="ground_name" label={t("groundName")} error={err("ground_name")}>
          {(a) => <Input {...a} required defaultValue={v("ground_name")} />}
        </Field>
        <Field name="ground_address" label={t("groundAddress")} error={err("ground_address")}>
          {(a) => <Input {...a} required defaultValue={v("ground_address")} />}
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field name="town" label={t("town")} error={err("town")}>
            {(a) => <Input {...a} required defaultValue={v("town")} />}
          </Field>
          <Fixed label={t("state")} value={t("stateName")} icon={<IconMapPin size={18} />} />
        </div>
        {fixed ? (
          <Fixed label={t("lga")} value={fixed.lga_name} icon={<IconMapPin size={18} />} />
        ) : (
          <Field name="lga_id" label={t("lga")} hint={t("lgaHint")} error={err("lga_id")} icon={<IconMapPin size={18} />}>
            {(a) => (
              <Select {...a} required defaultValue={v("lga_id")}>
                <option value="">{t("chooseLga")}</option>
                {open.length ? (
                  <optgroup label={t("lgaOpen")}>
                    {open.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </optgroup>
                ) : null}
                {/* Listed, not hidden, so a club can find its area and be told when it opens. */}
                {closed.length ? (
                  <optgroup label={t("lgaClosed")}>
                    {closed.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </optgroup>
                ) : null}
              </Select>
            )}
          </Field>
        )}
      </Fieldset>

      <Fieldset legend={t("contact")}>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field name="contact_phone" label={t("phone")} error={err("contact_phone")} icon={<IconPhone size={18} />}>
            {(a) => <PhoneInput {...a} required defaultValue={v("contact_phone")} />}
          </Field>
          <Field name="club_email" label={t("email")} error={err("club_email")} icon={<IconMail size={18} />}>
            {(a) => <Input {...a} type="email" required defaultValue={v("club_email")} />}
          </Field>
          <Field name="affiliation" label={t("affiliation")} optional optionalLabel={optional} error={err("affiliation")}>
            {(a) => <Input {...a} placeholder="Jigawa State FA" defaultValue={v("affiliation")} />}
          </Field>
        </div>
      </Fieldset>

      <Fieldset legend={t("second")}>
        <p className="-mt-2 text-xs text-muted">{t("secondHint")}</p>
        <Field name="official2_name" label={t("officialName")} error={err("official2_name")}>
          {(a) => <Input {...a} required defaultValue={v("official2_name")} />}
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field name="official2_role" label={t("officialRole")} error={err("official2_role")}>
            {(a) => (
              <Select {...a} required defaultValue={v("official2_role")}>
                <option value="">{t("choose")}</option>
                {OFFICIAL_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </Select>
            )}
          </Field>
          <Field name="official2_phone" label={t("officialPhone")} error={err("official2_phone")}>
            {(a) => <PhoneInput {...a} required defaultValue={v("official2_phone")} />}
          </Field>
        </div>
      </Fieldset>

      {stage2 ? (
        <Fieldset legend={t("sporting")}>
          <p className="-mt-2 text-xs text-muted">{t("sportingHint")}</p>
          <Field name="category" label={t("category")} error={err("category")}>
            {(a) => (
              <Select {...a} defaultValue={v("category")}>
                <option value="">{t("choose")}</option>
                {Object.entries(CATEGORIES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </Select>
            )}
          </Field>
          <Choices name="levels" legend={t("levels")} hint={t("levelsHint")} options={CLUB_LEVELS} chosen={chosenLevels} error={err("levels")} />
          <Choices name="age_groups" legend={t("ageGroups")} hint={t("ageGroupsHint")} options={AGE_GROUPS} chosen={chosenGroups} error={err("age_groups")} />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field name="cac_number" label={t("cac")} optional optionalLabel={optional} error={err("cac_number")}>
              {(a) => <Input {...a} defaultValue={v("cac_number")} />}
            </Field>
            <Field name="colours" label={t("colours")} optional optionalLabel={optional} error={err("colours")}>
              {(a) => <Input {...a} placeholder="Green and white" defaultValue={v("colours")} />}
            </Field>
            <Field name="website" label={t("website")} optional optionalLabel={optional} error={err("website")}>
              {(a) => <Input {...a} defaultValue={v("website")} />}
            </Field>
          </div>
        </Fieldset>
      ) : null}
    </div>
  );
}

/** A row of tickable pills: no JavaScript, the server checks the count. */
function Choices({ name, legend, hint, options, chosen, error }: {
  name: string;
  legend: string;
  hint: string;
  options: Record<string, string>;
  chosen: string[];
  error: string | null;
}) {
  return (
    <fieldset id={name} className="border-0 p-0" aria-describedby={error ? `${name}-error` : `${name}-hint`}>
      <legend className="font-bold">{legend}</legend>
      <p id={`${name}-hint`} className="mt-1 text-xs text-muted">{hint}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {Object.entries(options).map(([k, l]) => (
          <label key={k} htmlFor={`${name}_${k}`} className="inline-flex min-h-12 cursor-pointer items-center gap-2 rounded-pill border-2 border-line-strong px-4 has-[:checked]:border-pitch has-[:checked]:bg-check-bg">
            <input id={`${name}_${k}`} type="checkbox" name={name} value={k} defaultChecked={chosen.includes(k)} className="size-5 accent-[var(--pitch-deep)]" />
            {l}
          </label>
        ))}
      </div>
      {error ? (
        <p id={`${name}-error`} className="mt-2 flex items-start gap-2 font-bold text-danger">
          <IconRedCard size={20} className="mt-0.5 shrink-0" aria-hidden="true" />{error}
        </p>
      ) : null}
    </fieldset>
  );
}
