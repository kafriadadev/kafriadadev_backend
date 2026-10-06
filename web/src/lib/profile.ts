/**
 * The fixed choices on an athlete's record. A copy of the API's
 * contexts/identity/profile.py: a value offered here is one the API accepts.
 */

export const SPORTS = [
  "Football", "Athletics", "Basketball", "Volleyball", "Handball",
  "Boxing", "Wrestling", "Table Tennis", "Badminton", "Swimming",
] as const;

/** The pilot registers football only. The API still accepts the others above. */
export const PILOT_SPORT = "Football";

export const NOT_APPLICABLE = "Not applicable";

/** Position, or event, by sport. A sport not listed takes "Not applicable" only. */
export const POSITIONS: Record<string, readonly string[]> = {
  Football: ["Goalkeeper", "Centre-back", "Full-back", "Defensive midfielder",
    "Central midfielder", "Attacking midfielder", "Winger", "Striker"],
  Basketball: ["Point guard", "Shooting guard", "Small forward", "Power forward", "Centre"],
  Volleyball: ["Setter", "Outside hitter", "Middle blocker", "Opposite", "Libero"],
  Handball: ["Goalkeeper", "Wing", "Back", "Centre back", "Pivot"],
  Athletics: ["Sprints", "Hurdles", "Middle distance", "Long distance", "Jumps",
    "Throws", "Combined events", "Race walking"],
  Swimming: ["Freestyle", "Backstroke", "Breaststroke", "Butterfly", "Individual medley"],
};

export const NIGERIAN = "Nigerian";
export const NATIONALITIES = [
  NIGERIAN, "Beninese", "Cameroonian", "Chadian", "Ghanaian", "Nigerien", "Togolese", "Other",
] as const;

export const NIGERIAN_STATES = [
  "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
  "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
  "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
  "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
  "Yobe", "Zamfara",
] as const;

export const LEVELS: Record<string, string> = {
  school: "School",
  community: "Community or street",
  lga: "LGA team or league",
  state: "State team or league",
  national: "National league or team",
  international: "International",
};

export const GENDERS: Record<string, string> = { male: "Male", female: "Female" };

export const SIDES: Record<string, string> = { right: "Right", left: "Left", both: "Both" };
