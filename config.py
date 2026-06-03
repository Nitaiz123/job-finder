"""Configuration for the job finder. Tune these to your needs."""

import re

# Matches an explicit US state in a location string: ", CA" / ", NY" / ", TX,"
# Uses the 2-letter postal codes, bounded so it won't match random letters.
_US_STATE_CODES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
_US_STATE_RE = re.compile(
    r",\s*(" + "|".join(_US_STATE_CODES) + r")\b", re.IGNORECASE
)

# How recent must a posting be to count as "fresh"?
# Set to 168h (7 days) so jobs from Google, Amazon, Apple, Microsoft etc.
# that stay open for weeks are not filtered out immediately.
FRESHNESS_HOURS = 168

# Inclusion keywords: a job title must contain at least one of these (case-insensitive)
SWE_KEYWORDS = [
    # Core software engineering
    "software engineer",
    "software developer",
    "software development engineer",
    "sde",
    "sde i",
    "sde ii",
    "sde iii",
    "engineer i",
    "engineer ii",
    "engineer iii",
    "engineer iv",
    "engineer v",
    "programmer",
    "developer",
    # Specializations
    "backend engineer",
    "back-end engineer",
    "back end engineer",
    "frontend engineer",
    "front-end engineer",
    "front end engineer",
    "fullstack engineer",
    "full-stack engineer",
    "full stack engineer",
    "platform engineer",
    "infrastructure engineer",
    "infra engineer",
    "distributed systems",
    "systems engineer",
    "systems software",
    "site reliability",
    "sre",
    "devops engineer",
    "cloud engineer",
    "data engineer",
    "analytics engineer",
    # ML / AI
    "ml engineer",
    "machine learning engineer",
    "ai engineer",
    "applied scientist",
    "research engineer",
    "research scientist",
    "data scientist",
    # Security
    "security engineer",
    "iam engineer",
    "identity engineer",
    "application security",
    "appsec engineer",
    "cybersecurity engineer",
    "network engineer",
    # Developer tooling / productivity
    "api engineer",
    "developer experience",
    "developer productivity",
    "build engineer",
    "release engineer",
    "staff engineer",
    "principal engineer",
    # Mobile
    "ios engineer",
    "android engineer",
    "mobile engineer",
    "mobile developer",
    # Embedded / systems
    "embedded engineer",
    "embedded software",
    "robotics engineer",
    "computer vision engineer",
    # Other common titles
    "technical lead",
    "tech lead",
]

# Exclusion keywords: skip if title contains any of these
EXCLUDE_KEYWORDS = [
    "intern",
    "internship",
    "manager",
    " director",
    "vp ",
    " vp,",
    "head of",
    "sales engineer",
    "solutions engineer",
    "solution engineer",
    "customer engineer",
    "support engineer",
    "field engineer",
    "forward deployed",
    "recruiter",
    "technical recruiter",
    "qa engineer",
    "test engineer",
    "quality engineer",
    "hardware engineer",
    "firmware engineer",
    "mechanical engineer",
    "electrical engineer",
    "principal architect",
    "enterprise architect",
]

# ---------------------------------------------------------------------------
# Location / region configuration
# ---------------------------------------------------------------------------
# Each region is a list of substrings. A job's location string is matched
# (case-insensitive) against these. A job is kept if it matches ANY enabled
# region.
#
# IMPORTANT for work authorization:
#   US roles (and US-remote) are work-authorized under STEM OPT.
#   EU / UK / CANADA roles are NOT — they require visa sponsorship.
# The fetch layer tags every non-US, non-remote-US job with needs_sponsorship=1
# so the dashboard can flag and filter them honestly.

US_LOCATIONS = [
    "united states", "usa", "u.s.", "u.s.a", "us-",
    "san francisco", "sf bay", "bay area", "south san francisco", "palo alto", "mountain view",
    "sunnyvale", "san jose", "santa clara", "menlo park", "redwood city", "cupertino",
    "new york", "nyc", " ny ", " ny,",
    "seattle", "bellevue", "redmond",
    "austin", "dallas", "houston", " tx ", " tx,", ", texas",
    "boston", "cambridge", " ma ", " ma,",
    "los angeles", "santa monica", " la ", " la,",
    "chicago", " il ",
    "denver", "boulder",
    "atlanta",
    "miami",
    "portland",
    "washington dc", "washington, d.c", "arlington", "reston",
]

# Remote that is explicitly US or global-with-US — work-authorized.
REMOTE_US_LOCATIONS = [
    "remote - us", "remote (us", "remote, us", "us remote", "remote usa",
    "remote - united states", "remote, united states",
    "remote - americas", "remote - north america", "remote (americas",
]

# Ambiguous remote — could be anywhere. Kept, but treated as US-eligible
# only cautiously. We DON'T auto-flag bare "remote" as needing sponsorship,
# since many are US/global; the dashboard lets you filter.
REMOTE_AMBIGUOUS = [
    "remote", "anywhere", "distributed",
]

CANADA_LOCATIONS = [
    "canada", "toronto", "vancouver", "montreal", "montréal", "ottawa",
    "calgary", "edmonton", "waterloo", "kitchener", "mississauga",
    "ontario", "quebec", "québec", "british columbia", "alberta",
    "remote - canada", "remote (canada", "canada remote",
]

UK_LOCATIONS = [
    "united kingdom", "u.k.", "uk-", " uk ", " uk,", "england", "scotland",
    "wales", "london", "manchester", "edinburgh", "cambridge, uk",
    "bristol", "leeds", "glasgow", "birmingham, uk", "oxford",
    "remote - uk", "remote (uk", "uk remote",
]

EU_LOCATIONS = [
    "germany", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln",
    "france", "paris", "lyon", "toulouse",
    "netherlands", "amsterdam", "rotterdam", "the hague", "eindhoven", "utrecht",
    "ireland", "dublin", "cork",
    "spain", "madrid", "barcelona", "valencia",
    "italy", "milan", "milano", "rome", "roma", "turin",
    "poland", "warsaw", "krakow", "kraków", "wroclaw", "wrocław", "gdansk",
    "portugal", "lisbon", "lisboa", "porto",
    "sweden", "stockholm", "gothenburg",
    "denmark", "copenhagen",
    "norway", "oslo",
    "finland", "helsinki",
    "switzerland", "zurich", "zürich", "geneva", "lausanne",
    "austria", "vienna", "wien",
    "belgium", "brussels", "antwerp", "ghent",
    "czech", "prague", "praha", "brno",
    "romania", "bucharest", "cluj",
    "hungary", "budapest",
    "greece", "athens",
    "estonia", "tallinn",
    "lithuania", "vilnius",
    "latvia", "riga",
    "bulgaria", "sofia",
    "croatia", "zagreb",
    "luxembourg",
    "european union", "eu remote", "remote - eu", "remote (eu", "remote europe",
    "remote - europe", "emea",
]

# Toggle which regions are active. Set a region to False to exclude it entirely.
ENABLED_REGIONS = {
    "us": True,
    "remote_us": True,
    "remote_ambiguous": True,
    "canada": True,
    "uk": True,
    "eu": True,
}

# Map region key -> list of location substrings
REGION_MAP = {
    "us": US_LOCATIONS,
    "remote_us": REMOTE_US_LOCATIONS,
    "remote_ambiguous": REMOTE_AMBIGUOUS,
    "canada": CANADA_LOCATIONS,
    "uk": UK_LOCATIONS,
    "eu": EU_LOCATIONS,
}

# Which regions count as work-authorized under STEM OPT (no sponsorship needed)?
WORK_AUTHORIZED_REGIONS = {"us", "remote_us"}

# Backward-compat: some older code referenced LOCATION_FILTERS directly.
# Build it from all enabled regions so nothing breaks.
LOCATION_FILTERS = [
    loc
    for region, locs in REGION_MAP.items()
    if ENABLED_REGIONS.get(region, False)
    for loc in locs
]


def classify_location(location):
    """
    Classify a job location string into a region and decide sponsorship need.

    Returns (region_key, needs_sponsorship, matched_region_label).

    Disambiguation rules (order matters):
      1. Explicit remote-US -> authorized.
      2. Explicit foreign country name (", uk", ", united kingdom", ", germany",
         ", canada", etc.) wins over shared city names. This catches
         "Cambridge, UK" and "London, UK" correctly.
      3. Explicit US signal: ", <state code>" or "united states"/"usa".
         This catches "London, KY" and "Cambridge, MA" as US.
      4. Then bare city-name matching per region (US first), for strings that
         lack an explicit country/state.
      5. Bare remote/anywhere -> ambiguous, not flagged.
      6. Empty -> ambiguous, not flagged.
    """
    if not location:
        return ("remote_ambiguous", False, "Unspecified")

    loc = location.lower()

    def matches(region_key):
        return any(s in loc for s in REGION_MAP[region_key])

    # 1. Explicit remote-US.
    if ENABLED_REGIONS.get("remote_us") and matches("remote_us"):
        return ("remote_us", False, "Remote (US)")

    # 2. Explicit foreign-country tokens win over shared city names.
    #    These are strong, unambiguous signals.
    FOREIGN_COUNTRY_TOKENS = {
        "canada": ["canada", ", on,", ", on ", ", bc", ", qc", ", ab", "ontario", "quebec", "québec", "british columbia", "alberta"],
        "uk": ["united kingdom", ", uk", " uk,", "u.k.", ", england", ", scotland", ", wales"],
        "eu": [
            "germany", "france", "netherlands", "ireland", "spain", "italy",
            "poland", "portugal", "sweden", "denmark", "norway", "finland",
            "switzerland", "austria", "belgium", "czech", "romania", "hungary",
            "greece", "estonia", "lithuania", "latvia", "bulgaria", "croatia",
            "luxembourg", "european union",
        ],
    }
    for region_key, tokens in FOREIGN_COUNTRY_TOKENS.items():
        if ENABLED_REGIONS.get(region_key) and any(t in loc for t in tokens):
            label = {"canada": "Canada", "uk": "United Kingdom", "eu": "Europe (EU)"}[region_key]
            return (region_key, True, label)

    # 3. Explicit US signal: "united states"/"usa" or ", XX" state code.
    if ENABLED_REGIONS.get("us"):
        if any(s in loc for s in ["united states", "usa", "u.s.a", "u.s."]):
            return ("us", False, "United States")
        if _US_STATE_RE.search(location):
            return ("us", False, "United States")

    # 4. Bare city-name matching, US first to win shared names like "Cambridge".
    if ENABLED_REGIONS.get("us") and matches("us"):
        return ("us", False, "United States")
    if ENABLED_REGIONS.get("canada") and matches("canada"):
        return ("canada", True, "Canada")
    if ENABLED_REGIONS.get("uk") and matches("uk"):
        return ("uk", True, "United Kingdom")
    if ENABLED_REGIONS.get("eu") and matches("eu"):
        return ("eu", True, "Europe (EU)")

    # 5. Bare remote / anywhere.
    if ENABLED_REGIONS.get("remote_ambiguous") and matches("remote_ambiguous"):
        return ("remote_ambiguous", False, "Remote (unspecified)")

    # 6. Nothing matched.
    return (None, False, "Other")

# HTTP settings
REQUEST_TIMEOUT = 15
MAX_PARALLEL_REQUESTS = 20
USER_AGENT = "fresh-swe-jobs-finder/1.0 (personal job search tool)"

# ---------------------------------------------------------------------------
# Auto-discovery settings
# ---------------------------------------------------------------------------
# "conservative": validate every candidate before adding; cap validations/run (60).
# "aggressive":   add candidates faster, higher validation cap (500/run).
# "deep":         maximum throughput for the nightly deep-discovery workflow (2000/run).
DISCOVERY_MODE = "aggressive"

# A board (discovered or from a repo) is pruned after this many consecutive
# runs returning zero jobs. Curated seeds are never auto-pruned.
# Increased to 12 so seasonal companies (e.g. summer internship programs) aren't
# pruned during their off-season.
DISCOVERY_MAX_MISS_STREAK = 12

# Run discovery automatically as part of run.py? If False, run `python discover.py`
# manually. Discovery adds ~30-90s to a run depending on harvest size.
DISCOVERY_ON_EACH_RUN = True
