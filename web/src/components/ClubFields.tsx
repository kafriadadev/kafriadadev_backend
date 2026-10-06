import { getTranslations } from "next-intl/server";

import { IconMail, IconMapPin, IconPhone, IconRedCard, IconShirtSport } from "@/components/icons";
import { Field, Fieldset, Input, PhoneInput, Select } from "@/components/ui/Field";
import { AGE_GROUPS, CATEGORIES, CLUB_LEVELS, CLUB_TYPES, OFFICIAL_ROLES } from "@/lib/clubProfile";
import { PILOT_SPORT } from "@/lib/profile";

type Values = { get(key: string): string; all(key: string): string[] };

/**
 * The club's record as form fields: the same sections in sign-up, staff
 * registration and editing. Football only in the pilot. When editing, sport
 * and area are shown as fixed text, because a club that changed either would
 * be a different club.
 */
export async function ClubFields({
  values,
  badField,
  error,
  lgas,
  fixed,
}: {
  values: Values;
  badField: string;
  error: string;
  /** Areas open for registration. Omitted when editing. */
  lgas?: { id: string; name: string }[];
  /** When editing: the sport and area, not editable. */
  fixed?: { sport: string; lga_name: string };
}) {
  const t = await getTranslations("clubFields");
  const optional = (await getTranslations("ui"))("optional");
  const v = values.get;
  const err = (name: string) => (badField === name ? error : null);
  const chosenGroups = values.all("age_groups");
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
          <Field name="category" label={t("category")} error={err("category")}>
            {(a) => (
              <Select {...a} required defaultValue={v("category")}>
                <option value="">{t("choose")}</option>
                {Object.entries(CATEGORIES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </Select>
            )}
          </Field>
          <Field name="level" label={t("level")} error={err("level")}>
            {(a) => (
              <Select {...a} required defaultValue={v("level")}>
                <option value="">{t("choose")}</option>
                {Object.entries(CLUB_LEVELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </Select>
            )}
          </Field>
        </div>
        <fieldset id="age_groups" className="border-0 p-0" aria-describedby={err("age_groups") ? "age_groups-error" : "age_groups-hint"}>
          <legend className="font-bold">{t("ageGroups")}</legend>
          <p id="age_groups-hint" className="mt-1 text-xs text-muted">{t("ageGroupsHint")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(AGE_GROUPS).map(([k, l]) => (
              <label key={k} htmlFor={`age_${k}`} className="inline-flex min-h-12 cursor-pointer items-center gap-2 rounded-pill border-2 border-line-strong px-4 has-[:checked]:border-pitch has-[:checked]:bg-check-bg">
                <input id={`age_${k}`} type="checkbox" name="age_groups" value={k} defaultChecked={chosenGroups.includes(k)} className="size-5 accent-[var(--pitch-deep)]" />
                {l}
              </label>
            ))}
          </div>
          {err("age_groups") ? (
            <p id="age_groups-error" className="mt-2 flex items-start gap-2 font-bold text-danger">
              <IconRedCard size={20} className="mt-0.5 shrink-0" aria-hidden="true" />{error}
            </p>
          ) : null}
        </fieldset>
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
          {fixed ? (
            <Fixed label={t("lga")} value={fixed.lga_name} icon={<IconMapPin size={18} />} />
          ) : (
            <Field name="lga_id" label={t("lga")} error={err("lga_id")} icon={<IconMapPin size={18} />}>
              {(a) => (
                <Select {...a} required defaultValue={v("lga_id")}>
                  <option value="">{t("chooseLga")}</option>
                  {(lgas ?? []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </Select>
              )}
            </Field>
          )}
        </div>
      </Fieldset>

      <Fieldset legend={t("contact")}>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field name="contact_phone" label={t("phone")} error={err("contact_phone")} icon={<IconPhone size={18} />}>
            {(a) => <PhoneInput {...a} required defaultValue={v("contact_phone")} />}
          </Field>
          <Field name="club_email" label={t("email")} error={err("club_email")} icon={<IconMail size={18} />}>
            {(a) => <Input {...a} type="email" required defaultValue={v("club_email")} />}
          </Field>
          <Field name="cac_number" label={t("cac")} optional optionalLabel={optional} error={err("cac_number")}>
            {(a) => <Input {...a} defaultValue={v("cac_number")} />}
          </Field>
          <Field name="affiliation" label={t("affiliation")} optional optionalLabel={optional} error={err("affiliation")}>
            {(a) => <Input {...a} placeholder="Jigawa State FA" defaultValue={v("affiliation")} />}
          </Field>
          <Field name="colours" label={t("colours")} optional optionalLabel={optional} error={err("colours")}>
            {(a) => <Input {...a} placeholder="Green and white" defaultValue={v("colours")} />}
          </Field>
          <Field name="website" label={t("website")} optional optionalLabel={optional} error={err("website")}>
            {(a) => <Input {...a} defaultValue={v("website")} />}
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
    </div>
  );
}
