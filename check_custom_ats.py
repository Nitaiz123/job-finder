"""
Check if custom ATS entries (google/amazon/apple/microsoft) are present
in companies.json. Exit with code 1 if any are missing.
"""
import json
import sys

try:
    data = json.load(open("companies.json"))
except Exception as e:
    print(f"Could not read companies.json: {e}")
    sys.exit(1)

slugs = {c.get("slug", "") for c in data}
required = ["google", "amazon", "apple", "microsoft"]
missing = [s for s in required if s not in slugs]

if missing:
    print(f"Missing custom ATS entries: {', '.join(missing)}")
    sys.exit(1)
else:
    print(f"All custom ATS entries present ({', '.join(required)})")
    sys.exit(0)
