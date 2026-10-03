"""The fixed choices on an athlete's record, in one place.

The registration form, the details screen and the service all read from here, so
a value the form offers is always one the service accepts.
"""

from __future__ import annotations

SPORTS = (
    "Football", "Athletics", "Basketball", "Volleyball", "Handball",
    "Boxing", "Wrestling", "Table Tennis", "Badminton", "Swimming",
)

GENDERS = ("male", "female")

DOMINANT_SIDES = ("left", "right", "both")

# The highest level an athlete has played at, as a scout or coordinator reads it.
LEVELS = {
    "school": "School",
    "community": "Community or street",
    "lga": "LGA team or league",
    "state": "State team or league",
    "national": "National league or team",
    "international": "International",
}

NIGERIAN = "Nigerian"
NATIONALITIES = (
    NIGERIAN, "Beninese", "Cameroonian", "Chadian", "Ghanaian", "Nigerien", "Togolese", "Other",
)

# The 36 states and the Federal Capital Territory.
NIGERIAN_STATES = (
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
    "Yobe", "Zamfara",
)

HEIGHT_CM = (120, 230)
WEIGHT_KG = (35, 200)
YEARS_PLAYING = (0, 60)

NOT_APPLICABLE = "Not applicable"

# Position, or event, by sport. A sport not listed takes "Not applicable".
POSITIONS = {
    "Football": ("Goalkeeper", "Centre-back", "Full-back", "Defensive midfielder",
                 "Central midfielder", "Attacking midfielder", "Winger", "Striker"),
    "Basketball": ("Point guard", "Shooting guard", "Small forward", "Power forward", "Centre"),
    "Volleyball": ("Setter", "Outside hitter", "Middle blocker", "Opposite", "Libero"),
    "Handball": ("Goalkeeper", "Wing", "Back", "Centre back", "Pivot"),
    "Athletics": ("Sprints", "Hurdles", "Middle distance", "Long distance", "Jumps",
                  "Throws", "Combined events", "Race walking"),
    "Swimming": ("Freestyle", "Backstroke", "Breaststroke", "Butterfly", "Individual medley"),
}


def positions_for(sport: str) -> tuple[str, ...]:
    return (*POSITIONS.get(sport, ()), NOT_APPLICABLE)
