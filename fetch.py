"""
Main fetcher. Loads companies.json, fetches all jobs in parallel, applies
SWE/location/freshness filters, deduplicates against SQLite cache, writes
fresh jobs to jobs_latest.csv.
"""

import csv
import hashlib
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ats_clients import FETCHERS
from config import (
    FRESHNESS_HOURS, SWE_KEYWORDS, EXCLUDE_KEYWORDS,
    LOCATION_FILTERS, MAX_PARALLEL_REQUESTS, classify_location,
)

ROOT = Path(__file__).parent
COMPANIES_PATH = ROOT / "companies.json"
DB_PATH = ROOT / "jobs.db"
CSV_PATH = ROOT / "jobs_latest.csv"
JSON_PATH = ROOT / "jobs_latest.json"


def load_companies():
    if not COMPANIES_PATH.exists():
        print("ERROR: companies.json not found. Run bootstrap.py first.")
        sys.exit(1)
    return json.loads(COMPANIES_PATH.read_text())


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_hash TEXT PRIMARY KEY,
            company TEXT,
            title TEXT,
            location TEXT,
            region TEXT,
            needs_sponsorship INTEGER,
            url TEXT,
            first_seen_at TEXT,
            posted_at TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_first_seen ON seen_jobs(first_seen_at)
    """)
    # Migrate older DBs that lack the new columns.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
    if "region" not in cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN region TEXT")
    if "needs_sponsorship" not in cols:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN needs_sponsorship INTEGER")
    conn.commit()
    return conn


def job_hash(job):
    """Stable hash for repost detection. Title + company + first 500 chars of JD."""
    key = "|".join([
        job["company"].lower().strip(),
        job["title"].lower().strip(),
        job["description_snippet"][:300].lower().strip(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def is_swe(title):
    title_lower = title.lower()
    if any(ex in title_lower for ex in EXCLUDE_KEYWORDS):
        return False
    return any(kw in title_lower for kw in SWE_KEYWORDS)


# ---------------------------------------------------------------------------
# Experience level detection — parsed from job description text
# ---------------------------------------------------------------------------
import re as _re

# Matches patterns like:
#   "3+ years", "3-5 years", "at least 5 years", "minimum 2 years",
#   "5 or more years", "2 to 4 years of experience"
_YOE_RE = _re.compile(
    r"""(?ix)
    (?:
        (\d+)\s*(?:\+|\s*or\s*more|\s*\+)   # "5+" or "5 or more"
        |                                     # OR
        (\d+)\s*[-–to]+\s*(\d+)              # "3-5" or "3 to 5"
        |                                     # OR
        (?:at\s+least|minimum\s+of?|\bmin\.?)\s*(\d+)  # "at least 3"
        |                                     # OR
        (\d+)\s*(?:years?|yrs?)              # bare "3 years"
    )
    \s*(?:years?|yrs?)?\s*
    (?:of\s+)?(?:professional\s+)?(?:relevant\s+)?experience
    """,
    _re.IGNORECASE | _re.VERBOSE,
)


def _extract_years(text: str):
    """
    Scan text for the first explicit years-of-experience requirement.
    Returns the minimum years as a float, or None if not found.
    """
    for m in _YOE_RE.finditer(text):
        # Group 1: "N+" or "N or more"  -> min = N
        if m.group(1):
            return float(m.group(1))
        # Groups 2+3: "N-M" range -> min = N
        if m.group(2) and m.group(3):
            return float(m.group(2))
        # Group 4: "at least N" / "minimum N"
        if m.group(4):
            return float(m.group(4))
        # Group 5: bare "N years of experience"
        if m.group(5):
            return float(m.group(5))
    return None


def classify_exp_level(title: str, description: str = "") -> str:
    """
    Classify a job by years-of-experience requirement extracted from the JD.
    Buckets:
      0-2  -> "0-2 years"
      3-5  -> "3-5 years"
      5+   -> "5+ years"
      None -> "Unspecified"
    Falls back to title heuristics only when the JD yields nothing.
    """
    text = (description or "").strip()
    years = _extract_years(text) if text else None

    # Title-based fallback when JD has no explicit requirement.
    # Any title that signals seniority -> 5+ years.
    # Any title that signals entry level -> 0-2 years.
    if years is None:
        t = " " + (title or "").lower() + " "
        SENIOR_SIGNALS = [
            "senior ", "senior-", " sr.", " sr ", "sr. ",
            "staff ", "principal ", "distinguished ",
            "lead ", " lead,", "tech lead", "technical lead",
            "director", "architect", "head of",
            "manager", "vp ", " vp,",
        ]
        ENTRY_SIGNALS = [
            "junior", " jr.", " jr ", "associate ",
            "new grad", "entry level", "entry-level",
            " i ", " i,", " level 1", " level i ",
        ]
        if any(p in t for p in SENIOR_SIGNALS):
            return "5+ years"
        if any(p in t for p in ENTRY_SIGNALS):
            return "0-2 years"
        return "Unspecified"

    if years <= 2:
        return "0-2 years"
    if years <= 5:
        return "3-5 years"
    return "5+ years"


def location_region(location):
    """
    Returns (kept, region_key, needs_sponsorship, region_label).
    kept=False means the location didn't match any enabled region -> drop it.
    """
    region_key, needs_sponsorship, label = classify_location(location)
    return (region_key is not None, region_key, needs_sponsorship, label)


def is_fresh(posted_at_iso):
    if not posted_at_iso:
        return False
    try:
        posted = datetime.fromisoformat(posted_at_iso.replace("Z", "+00:00"))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_HOURS)
        return posted >= cutoff
    except (ValueError, TypeError):
        return False


def fetch_one(company):
    fetcher = FETCHERS.get(company["ats"])
    if not fetcher:
        return []
    try:
        return fetcher(company["slug"])
    except Exception as e:
        # Don't let one company kill the whole run
        return []


def fetch_all(companies):
    all_jobs = []
    job_counts_by_board = {}  # (ats, slug) -> count, for board-health tracking
    completed = 0
    total = len(companies)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as executor:
        futures = {executor.submit(fetch_one, c): c for c in companies}
        for fut in as_completed(futures):
            completed += 1
            company = futures[fut]
            jobs = fut.result()
            all_jobs.extend(jobs)
            job_counts_by_board[(company["ats"], company["slug"])] = len(jobs)
            if completed % 25 == 0 or completed == total:
                print(f"  Fetched {completed}/{total} companies, "
                      f"{len(all_jobs)} total postings so far")

    return all_jobs, job_counts_by_board


def filter_and_dedupe(all_jobs, conn):
    """Apply SWE/location/freshness filters, attach region + sponsorship,
    then check repost status."""
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    pre_filter = len(all_jobs)
    swe_jobs = [j for j in all_jobs if is_swe(j["title"])]

    # Location filter + region tagging in one pass.
    loc_filtered = []
    for j in swe_jobs:
        kept, region_key, needs_sp, label = location_region(j["location"])
        if not kept:
            continue
        j["region"] = region_key or ""
        j["region_label"] = label
        j["needs_sponsorship"] = 1 if needs_sp else 0
        loc_filtered.append(j)

    fresh_jobs = [j for j in loc_filtered if is_fresh(j["posted_at"])]

    print(f"\nFiltering funnel:")
    print(f"  Total postings:        {pre_filter}")
    print(f"  After SWE filter:      {len(swe_jobs)}")
    print(f"  After location filter: {len(loc_filtered)}")
    print(f"  After freshness ({FRESHNESS_HOURS}h): {len(fresh_jobs)}")

    new_jobs = []
    repost_count = 0
    for job in fresh_jobs:
        h = job_hash(job)
        cur.execute("SELECT first_seen_at FROM seen_jobs WHERE job_hash = ?", (h,))
        row = cur.fetchone()
        if row:
            repost_count += 1
            continue
        cur.execute("""
            INSERT INTO seen_jobs
                (job_hash, company, title, location, region, needs_sponsorship,
                 url, first_seen_at, posted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (h, job["company"], job["title"], job["location"],
              job.get("region", ""), job.get("needs_sponsorship", 0),
              job["url"], now_iso, job["posted_at"]))
        job["job_hash"] = h
        new_jobs.append(job)

    conn.commit()
    print(f"  After repost dedupe:   {len(new_jobs)} (skipped {repost_count} reposts)")

    # Regional breakdown of the new jobs.
    if new_jobs:
        auth = sum(1 for j in new_jobs if not j.get("needs_sponsorship"))
        sponsor = len(new_jobs) - auth
        print(f"\nWork authorization breakdown (new jobs):")
        print(f"  Work-authorized (US / remote-US / remote): {auth}")
        print(f"  Needs sponsorship (EU / UK / Canada):      {sponsor}")
        by_region = {}
        for j in new_jobs:
            by_region[j.get("region_label", "Other")] = by_region.get(j.get("region_label", "Other"), 0) + 1
        for label, n in sorted(by_region.items(), key=lambda x: -x[1]):
            print(f"    {label}: {n}")

    return new_jobs


def write_csv(jobs):
    fields = ["company", "ats", "title", "location", "region_label",
              "needs_sponsorship", "department", "posted_at", "url", "job_hash"]
    ordered = sorted(jobs, key=lambda x: (x.get("needs_sponsorship", 0),
                                          _neg_time(x.get("posted_at", ""))))
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for j in ordered:
            w.writerow(j)
    print(f"\nWrote {len(jobs)} jobs to {CSV_PATH}")


def write_json(new_jobs):
    """
    Merge new jobs with the existing accumulated jobs_latest.json so that
    old jobs never disappear from the dashboard. Deduplication is done by
    job_hash. New jobs are marked with is_new=True so the dashboard can
    highlight them. Sorted newest-first.
    """
    # Load existing accumulated records, keyed by job_hash.
    existing: dict = {}
    if JSON_PATH.exists():
        try:
            for rec in json.loads(JSON_PATH.read_text(encoding="utf-8")):
                h = rec.get("job_hash", "")
                if h:
                    rec["is_new"] = False   # clear stale new-flag
                    existing[h] = rec
        except Exception:
            pass  # corrupt file — start fresh

    # Build records for the new jobs and merge.
    now_iso = datetime.now(timezone.utc).isoformat()
    for j in new_jobs:
        h = j.get("job_hash", "")
        # Preserve original first_seen_at if this job was already accumulated.
        # Only set it to now for truly new jobs.
        original_first_seen = existing.get(h, {}).get("first_seen_at", "")
        is_truly_new = h not in existing
        rec = {
            "company": j.get("company", ""),
            "ats": j.get("ats", ""),
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "region_label": j.get("region_label", ""),
            "needs_sponsorship": j.get("needs_sponsorship", 0),
            "department": j.get("department", ""),
            "posted_at": j.get("posted_at", ""),
            "first_seen_at": original_first_seen if original_first_seen else now_iso,
            "url": j.get("url", ""),
            "job_hash": h,
            "description_full": j.get("description_full", "") or j.get("description_snippet", ""),
            "exp_level": classify_exp_level(
                j.get("title", ""),
                j.get("description_full", "") or j.get("description_snippet", ""),
            ),
            "is_new": is_truly_new,
        }
        existing[h] = rec

    # Drop jobs older than 60 days to keep the JSON file size manageable.
    cutoff = datetime.now(timezone.utc).timestamp() - 60 * 86400
    pruned = 0
    for h in list(existing.keys()):
        rec = existing[h]
        ts = _neg_time(rec.get("first_seen_at", "") or rec.get("posted_at", ""))
        if ts != 0 and -ts < cutoff:  # _neg_time returns negative timestamp
            del existing[h]
            pruned += 1
    if pruned:
        print(f"Pruned {pruned} jobs older than 60 days from accumulated JSON")

    # Truncate description_full to 3000 chars to keep file size manageable.
    # The modal popup shows the full description but 3000 chars is enough for display.
    MAX_DESC = 3000
    for rec in existing.values():
        if rec.get("description_full") and len(rec["description_full"]) > MAX_DESC:
            rec["description_full"] = rec["description_full"][:MAX_DESC] + "…"

    # Sort: newest first (by first_seen_at, then posted_at).
    all_records = sorted(
        existing.values(),
        key=lambda x: (
            x.get("needs_sponsorship", 0),
            _neg_time(x.get("first_seen_at", "") or x.get("posted_at", "")),
        ),
    )

    # Write minified JSON (no indent) to save space.
    JSON_PATH.write_text(json.dumps(all_records, separators=(',', ':')), encoding="utf-8")
    print(f"Wrote {len(all_records)} accumulated records to {JSON_PATH} "
          f"({len(new_jobs)} new this run)")


def _neg_time(iso):
    """Helper for sorting: more recent = smaller sort key."""
    try:
        return -datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return 0


def main():
    print(f"=== Fresh SWE Jobs Finder ===")
    print(f"Freshness window: last {FRESHNESS_HOURS}h\n")

    companies = load_companies()
    print(f"Loaded {len(companies)} companies from companies.json")
    by_ats = {}
    for c in companies:
        by_ats.setdefault(c["ats"], 0)
        by_ats[c["ats"]] += 1
    for ats, n in sorted(by_ats.items()):
        print(f"  {ats}: {n}")

    print(f"\nFetching jobs from all ATSes in parallel...")
    all_jobs, job_counts_by_board = fetch_all(companies)

    conn = init_db()
    new_jobs = filter_and_dedupe(all_jobs, conn)
    conn.close()

    write_csv(new_jobs)
    write_json(new_jobs)

    # Update board health (miss streaks) and prune long-dead non-curated boards.
    try:
        from discover import update_board_health
        update_board_health(job_counts_by_board)
    except Exception as e:
        print(f"  (board-health update skipped: {e})")

    return new_jobs


if __name__ == "__main__":
    main()
