"""
Check if custom ATS entries (google/amazon/apple/microsoft) are present
in companies.json with the correct ATS type. Exit with code 1 if any are
missing or have the wrong ATS (e.g. microsoft mapped to jobvite).
Also fixes wrong ATS assignments in-place.
"""
import json
import sys

CUSTOM_ATS = {
    "google": "google",
    "amazon": "amazon",
    "apple": "apple",
    "microsoft": "microsoft",
    "snapchat|wd1|snap": "workday",
}

try:
    data = json.load(open("companies.json"))
except Exception as e:
    print(f"Could not read companies.json: {e}")
    sys.exit(1)

slug_map = {c.get("slug", ""): c for c in data}
missing = []
fixed = []

for slug, expected_ats in CUSTOM_ATS.items():
    if slug not in slug_map:
        missing.append(slug)
    elif slug_map[slug].get("ats") != expected_ats:
        old_ats = slug_map[slug]["ats"]
        slug_map[slug]["ats"] = expected_ats
        slug_map[slug]["miss_streak"] = 0
        fixed.append(f"{slug}: {old_ats} -> {expected_ats}")

if fixed:
    print(f"Fixed ATS assignments: {', '.join(fixed)}")
    with open("companies.json", "w") as f:
        json.dump(data, f, indent=2)
    print("companies.json updated.")

if missing:
    print(f"Missing custom ATS entries: {', '.join(missing)}")
    sys.exit(1)
elif fixed:
    # Fixed entries — signal that bootstrap should re-validate
    print("ATS entries fixed in-place, no bootstrap needed.")
    sys.exit(0)
else:
    print(f"All custom ATS entries present and correct ({', '.join(CUSTOM_ATS.keys())})")
    sys.exit(0)
