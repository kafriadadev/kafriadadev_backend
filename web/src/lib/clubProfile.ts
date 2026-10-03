/**
 * A club's record: the fixed choices (a copy of the API's contexts/clubs/profile.py)
 * and reading the shared club fields out of a submitted form.
 */

export const CLUB_TYPES: Record<string, string> = {
  club: "Club", academy: "Academy", school: "School team",
};
export const CATEGORIES: Record<string, string> = { men: "Men", women: "Women", mixed: "Mixed" };
export const AGE_GROUPS: Record<string, string> = {
  senior: "Senior", u20: "Under 20", u17: "Under 17", u15: "Under 15", u13: "Under 13",
};
export const CLUB_LEVELS: Record<string, string> = {
  grassroots: "Grassroots", amateur: "Amateur league",
  semi_pro: "Semi-professional", professional: "Professional",
};
export const OFFICIAL_ROLES = [
  "Chairman", "Secretary", "Manager", "Head coach", "Owner", "Treasurer",
] as const;

export type ClubProfile = {
  short_name: string;
  type: string;
  category: string;
  age_groups: string[];
  level: string;
  year_founded: number;
  ground_name: string;
  ground_address: string;
  town: string;
  club_email: string;
  official2_name: string;
  official2_role: string;
  official2_phone: string;
  cac_number: string | null;
  affiliation: string | null;
  colours: string | null;
  website: string | null;
};

/** Text fields of the club form, in the order they are kept on a bounce-back. */
export const CLUB_TEXT_FIELDS = [
  "name", "short_name", "type", "sport", "category", "level", "year_founded", "lga_id",
  "ground_name", "ground_address", "town", "contact_phone", "club_email", "cac_number",
  "affiliation", "colours", "website", "official2_name", "official2_role", "official2_phone",
] as const;

/** Read the club fields from a form. `year` is NaN when it is not a whole number. */
export function readClub(formData: FormData) {
  const text = (k: string) => String(formData.get(k) ?? "").trim();
  const year = Number(text("year_founded"));
  const profile: ClubProfile = {
    short_name: text("short_name"),
    type: text("type"),
    category: text("category"),
    age_groups: formData.getAll("age_groups").map(String),
    level: text("level"),
    year_founded: Number.isInteger(year) && text("year_founded") ? year : Number.NaN,
    ground_name: text("ground_name"),
    ground_address: text("ground_address"),
    town: text("town"),
    club_email: text("club_email"),
    official2_name: text("official2_name"),
    official2_role: text("official2_role"),
    official2_phone: text("official2_phone"),
    cac_number: text("cac_number") || null,
    affiliation: text("affiliation") || null,
    colours: text("colours") || null,
    website: text("website") || null,
  };
  const kept = new URLSearchParams();
  for (const k of CLUB_TEXT_FIELDS) if (text(k)) kept.set(k, text(k));
  for (const g of profile.age_groups) kept.append("age_groups", g);
  return {
    name: text("name"),
    sport: text("sport"),
    lga_id: text("lga_id"),
    contact_phone: text("contact_phone"),
    profile,
    kept,
  };
}
