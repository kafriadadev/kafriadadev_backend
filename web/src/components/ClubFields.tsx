import { PILOT_SPORT } from "@/lib/profile";
import {
  AGE_GROUPS, CATEGORIES, CLUB_LEVELS, CLUB_TYPES, OFFICIAL_ROLES,
} from "@/lib/clubProfile";

type Values = { get(key: string): string; all(key: string): string[] };

/**
 * The club's record as form fields: the same sections in sign-up, staff
 * registration and editing. Sport and area are shown as fixed text when editing,
 * because a club that changed either would be a different club.
 */
export function ClubFields({
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
  const Field = ({
    name, label, hint, children,
  }: { name: string; label: string; hint?: string; children: React.ReactNode }) => (
    <div>
      <label htmlFor={name}>{label}</label>
      {hint ? <span>{hint}</span> : null}
      {children}
      {badField === name ? <span>{error}</span> : null}
    </div>
  );
  const v = values.get;
  const chosenGroups = values.all("age_groups");

  return (
    <>
      <fieldset>
        <legend>The club</legend>
        <Field name="name" label="Registered name" hint="As the club is known officially.">
          <input id="name" name="name" required defaultValue={v("name")} />
        </Field>
        <div>
          <Field name="short_name" label="Short name" hint="For example JFC.">
            <input id="short_name" name="short_name" required maxLength={20} defaultValue={v("short_name")} />
          </Field>
          <Field name="year_founded" label="Year founded">
            <input id="year_founded" name="year_founded" type="number" inputMode="numeric"
              min={1900} required placeholder="2015" defaultValue={v("year_founded")} />
          </Field>
        </div>
        <div>
          <Field name="type" label="Kind of club">
            <select id="type" name="type" required defaultValue={v("type")}>
              <option value="">Choose</option>
              {Object.entries(CLUB_TYPES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          {fixed ? (
            <div>
              <label>Sport</label>
              <p>{fixed.sport}</p>
            </div>
          ) : (
            <input type="hidden" name="sport" value={PILOT_SPORT} />
          )}
        </div>
        <div>
          <Field name="category" label="Category">
            <select id="category" name="category" required defaultValue={v("category")}>
              <option value="">Choose</option>
              {Object.entries(CATEGORIES).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          <Field name="level" label="Level">
            <select id="level" name="level" required defaultValue={v("level")}>
              <option value="">Choose</option>
              {Object.entries(CLUB_LEVELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
        </div>
        <div>
          <span>Age groups</span>
          <span>Tick every age group the club fields a team in.</span>
          <div>
            {Object.entries(AGE_GROUPS).map(([k, l]) => (
              <label key={k} htmlFor={`age_${k}`}>
                <input id={`age_${k}`} type="checkbox" name="age_groups" value={k}
                  defaultChecked={chosenGroups.includes(k)} />
                {l}
              </label>
            ))}
          </div>
          {badField === "age_groups" ? <span>{error}</span> : null}
        </div>
      </fieldset>

      <fieldset>
        <legend>Home ground</legend>
        <Field name="ground_name" label="Ground or training venue">
          <input id="ground_name" name="ground_name" required defaultValue={v("ground_name")} />
        </Field>
        <Field name="ground_address" label="Address">
          <input id="ground_address" name="ground_address" required defaultValue={v("ground_address")} />
        </Field>
        <div>
          <Field name="town" label="Town">
            <input id="town" name="town" required defaultValue={v("town")} />
          </Field>
          {fixed ? (
            <div>
              <label>Local government area</label>
              <p>{fixed.lga_name}</p>
            </div>
          ) : (
            <Field name="lga_id" label="Local government area">
              <select id="lga_id" name="lga_id" required defaultValue={v("lga_id")}>
                <option value="">Choose an area</option>
                {(lgas ?? []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </Field>
          )}
        </div>
      </fieldset>

      <fieldset>
        <legend>Official contact</legend>
        <div>
          <Field name="contact_phone" label="Club phone">
            <input id="contact_phone" name="contact_phone" type="tel" inputMode="tel" required
              placeholder="0803 000 0000" defaultValue={v("contact_phone")} />
          </Field>
          <Field name="club_email" label="Club email">
            <input id="club_email" name="club_email" type="email" required defaultValue={v("club_email")} />
          </Field>
        </div>
        <div>
          <Field name="cac_number" label="CAC or registration number (optional)">
            <input id="cac_number" name="cac_number" defaultValue={v("cac_number")} />
          </Field>
          <Field name="affiliation" label="FA or league affiliation (optional)">
            <input id="affiliation" name="affiliation" placeholder="Jigawa State FA"
              defaultValue={v("affiliation")} />
          </Field>
        </div>
        <div>
          <Field name="colours" label="Club colours (optional)">
            <input id="colours" name="colours" placeholder="Green and white" defaultValue={v("colours")} />
          </Field>
          <Field name="website" label="Website or social page (optional)">
            <input id="website" name="website" defaultValue={v("website")} />
          </Field>
        </div>
      </fieldset>

      <fieldset>
        <legend>Second official</legend>
        <p>Someone else at the club we can reach.</p>
        <Field name="official2_name" label="Full name">
          <input id="official2_name" name="official2_name" required defaultValue={v("official2_name")} />
        </Field>
        <div>
          <Field name="official2_role" label="Role">
            <select id="official2_role" name="official2_role" required defaultValue={v("official2_role")}>
              <option value="">Choose</option>
              {OFFICIAL_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          <Field name="official2_phone" label="Phone">
            <input id="official2_phone" name="official2_phone" type="tel" inputMode="tel" required
              defaultValue={v("official2_phone")} />
          </Field>
        </div>
      </fieldset>
    </>
  );
}
