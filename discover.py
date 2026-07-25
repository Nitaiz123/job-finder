"""
Conservative auto-discovery of new ATS boards.

Philosophy: grow companies.json over time WITHOUT polluting it with dead or
junk boards. A discovered candidate is only persisted permanently after it
*validates* — i.e. its ATS endpoint returns at least one real job. Boards that
miss (404 / empty) for several consecutive runs get pruned.

companies.json schema (v2):
[
  {
    "slug": "stripe",
    "ats": "greenhouse",
    "source": "curated" | "simplify" | "discovered",
    "added_at": "2026-05-20T...",
    "last_validated_at": "2026-05-20T...",
    "miss_streak": 0,            # consecutive runs with no jobs
    "last_job_count": 42
  },
  ...
]

Backward compatible: old entries that are just {"slug","ats"} are upgraded
on first load.

Discovery sources (all public):
  1. Simplify GitHub repos (re-crawled each run; grows as PRs land)
  2. 60+ additional public job-board aggregator repos (all sectors)
  3. CareerPuck sitemap (direct enumeration of all CareerPuck tenants)
  4. Trusted curated company lists (YC, Forbes, etc.) scraped for ATS links
  5. Parallel validation with 20 workers for speed

Validation is the gate. We never trust a candidate slug until it returns jobs.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

from ats_clients import FETCHERS
from config import USER_AGENT, REQUEST_TIMEOUT, DISCOVERY_MODE, DISCOVERY_MAX_MISS_STREAK

ROOT = Path(__file__).parent
COMPANIES_PATH = ROOT / "companies.json"
CANDIDATES_PATH = ROOT / "discovery_candidates.json"  # pending, unvalidated

# ---------------------------------------------------------------------------
# Discovery source URLs — all public GitHub repos containing raw ATS links
# ---------------------------------------------------------------------------
EXTRA_SOURCE_URLS = [
    # ---- Simplify repos — primary source ----
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README-Off-Season.md",

    # ---- Community SWE job-tracking repos ----
    "https://raw.githubusercontent.com/speedyapply/2025-AI-College-Jobs/main/README.md",
    "https://raw.githubusercontent.com/speedyapply/2026-SWE-College-Jobs/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Software-Engineer-Jobs/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2026-Software-Engineer-Jobs/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Software-Engineer-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2026-Software-Engineer-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Software-Engineer-New-Grad/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Backend-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2026-Backend-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Backend-New-Grad/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-ML-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2026-ML-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-ML-New-Grad/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Data-Science-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2026-Data-Science-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Data-Science-New-Grad/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Cyber-Security-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2026-Cyber-Security-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Cyber-Security-New-Grad/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-DevOps-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-DevOps-New-Grad/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-IT-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Product-Management-Internship/main/README.md",

    # ---- Sector-specific repos ----
    "https://raw.githubusercontent.com/jobright-ai/2025-Health-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Finance-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Marketing-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Sales-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Legal-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Accounting-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Management-Consulting-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Business-Analyst-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Operations-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Mechanical-Engineering-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Electrical-Engineering-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Aerospace-Internship/main/README.md",
    "https://raw.githubusercontent.com/jobright-ai/2025-Bioengineering-Internship/main/README.md",

    # ---- New-grad / off-season repos ----
    "https://raw.githubusercontent.com/ReaVNaiL/New-Grad-2024/main/README.md",
    "https://raw.githubusercontent.com/pittcsc/NewGrad-Positions/dev/README.md",
    "https://raw.githubusercontent.com/coderQuad/New-Grad-Positions-2023/master/README.md",
    "https://raw.githubusercontent.com/alenachao/New-Grad-2025/main/README.md",
    "https://raw.githubusercontent.com/Ouckah/Summer2025-Internships/dev/README.md",
    "https://raw.githubusercontent.com/cvrve/Summer2025-Internships/dev/README.md",
    "https://raw.githubusercontent.com/vanshb03/Summer2026-Internships/dev/README.md",

    # ---- Remote / hiring culture repos ----
    "https://raw.githubusercontent.com/remoteintech/remote-jobs/main/README.md",
    "https://raw.githubusercontent.com/lukasz-madon/awesome-remote-job/master/README.md",
    "https://raw.githubusercontent.com/poteto/hiring-without-whiteboards/master/README.md",
    "https://raw.githubusercontent.com/j-delaney/easy-application/master/README.md",
    "https://raw.githubusercontent.com/cassidoo/getting-a-gig/master/README.md",

    # ---- Finance / quant ----
    "https://raw.githubusercontent.com/pittcsc/NewGrad-Positions/dev/README.md",

    # ---- Awesome lists with company links ----
    "https://raw.githubusercontent.com/engineerapart/TheRemoteFreelancer/master/README.md",
    "https://raw.githubusercontent.com/tramcar/tramcar/main/README.md",
]

# ---------------------------------------------------------------------------
# Trusted curated company list sources — scraped for ATS links directly
# These are high-quality sources (YC, Forbes, etc.) that list real companies
# ---------------------------------------------------------------------------
CURATED_COMPANY_LIST_URLS = [
    # Y Combinator companies — top startup source
    "https://raw.githubusercontent.com/yc-oss/api/main/batches/all.json",
    # Awesome YC companies list
    "https://raw.githubusercontent.com/dsernst/awesome-yc-companies/master/README.md",
    # Unicorn companies list
    "https://raw.githubusercontent.com/nicholasgasior/unicorn-companies/master/README.md",
    # Tech company career pages list
    "https://raw.githubusercontent.com/tramcar/tramcar/main/README.md",
    # H1B sponsoring companies (large employers)
    "https://raw.githubusercontent.com/nicholasgasior/h1b-data/master/README.md",
    # Awesome startups
    "https://raw.githubusercontent.com/KrishMunot/awesome-startup/master/README.md",
    # Tech companies with good eng culture
    "https://raw.githubusercontent.com/Twipped/InterviewThis/master/README.md",
]

ATS_PATTERNS = {
    "greenhouse": [
        re.compile(r"boards\.greenhouse\.io/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"job-boards\.greenhouse\.io/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"job-boards\.eu\.greenhouse\.io/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"greenhouse\.io/([a-z0-9][a-z0-9\-]*)/jobs", re.IGNORECASE),
    ],
    "lever": [
        re.compile(r"jobs\.lever\.co/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"lever\.co/([a-z0-9][a-z0-9\-]*)/jobs", re.IGNORECASE),
    ],
    "ashby": [
        re.compile(r"jobs\.ashbyhq\.com/([a-z0-9][a-z0-9\.\-]*)", re.IGNORECASE),
        re.compile(r"ashbyhq\.com/([a-z0-9][a-z0-9\.\-]*)", re.IGNORECASE),
    ],
    "workable": [
        re.compile(r"apply\.workable\.com/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"workable\.com/([a-z0-9][a-z0-9\-]*)/jobs", re.IGNORECASE),
    ],
    "eightfold": [
        re.compile(r"([a-z0-9][a-z0-9\-]*)\.eightfold\.ai", re.IGNORECASE),
    ],
    "icims": [
        re.compile(r"careers-([a-z0-9][a-z0-9\-]*)\.icims\.com", re.IGNORECASE),
        re.compile(r"(?<![a-z\-])([a-z0-9][a-z0-9\-]+)\.icims\.com", re.IGNORECASE),
    ],
    "smartrecruiters": [
        re.compile(r"jobs\.smartrecruiters\.com/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"smartrecruiters\.com/([a-z0-9][a-z0-9\-]*)/jobs", re.IGNORECASE),
    ],
    "jobvite": [
        re.compile(r"jobs\.jobvite\.com/([a-z0-9][a-z0-9\-]*)/jobs", re.IGNORECASE),
        re.compile(r"jobs\.jobvite\.com/careers/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
    ],
    "rippling": [
        re.compile(r"ats\.rippling\.com/([a-z0-9][a-z0-9\-]*)/jobs", re.IGNORECASE),
        re.compile(r"rippling\.com/job-board/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
    ],
    "recruitee": [
        re.compile(r"([a-z0-9][a-z0-9\-]*)\.recruitee\.com", re.IGNORECASE),
    ],
    # Workday intentionally excluded from discovery: its compound tenant|host|site
    # slug can't be reliably inferred from a URL alone without verification.
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def fetch_text(url):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.text
    except requests.RequestException:
        pass
    return None


def load_companies():
    """Load companies.json and upgrade any v1 entries to v2 schema."""
    if not COMPANIES_PATH.exists():
        return []
    raw = json.loads(COMPANIES_PATH.read_text())
    upgraded = []
    for entry in raw:
        if "source" not in entry:
            entry = {
                "slug": entry["slug"],
                "ats": entry["ats"],
                "source": "curated",
                "added_at": _now(),
                "last_validated_at": None,
                "miss_streak": 0,
                "last_job_count": None,
            }
        upgraded.append(entry)
    return upgraded


def save_companies(companies):
    COMPANIES_PATH.write_text(json.dumps(companies, indent=2))


def load_candidates():
    if not CANDIDATES_PATH.exists():
        return {}
    return json.loads(CANDIDATES_PATH.read_text())


def save_candidates(candidates):
    CANDIDATES_PATH.write_text(json.dumps(candidates, indent=2))


def harvest_careerpuck_sitemap():
    """
    CareerPuck publishes a public sitemap listing every company job board:
      https://app.careerpuck.com/sitemap.xml
    with entries like https://app.careerpuck.com/job-board/{company}.

    This is a first-class discovery source — it enumerates ALL CareerPuck
    tenants directly, not just ones mentioned in third-party repos.
    """
    found = set()
    text = fetch_text("https://app.careerpuck.com/sitemap.xml")
    if not text:
        return found
    pattern = re.compile(r"https://app\.careerpuck\.com/job-board/([a-z0-9][a-z0-9\-]*)",
                         re.IGNORECASE)
    for m in pattern.findall(text):
        slug = m.lower().strip().strip("-.")
        if slug and len(slug) > 1:
            found.add(("careerpuck", slug))
    return found


def harvest_yc_companies():
    """
    Harvest ATS slugs from Y Combinator's public company API.
    YC publishes a JSON list of all their portfolio companies at:
      https://raw.githubusercontent.com/yc-oss/api/main/batches/all.json
    Each entry has a 'website' field. We fetch each company's careers page
    and look for ATS links.

    To avoid hammering hundreds of sites, we only check companies that have
    a 'jobs_url' field pointing directly to an ATS.
    """
    found = set()
    text = fetch_text("https://raw.githubusercontent.com/yc-oss/api/main/batches/all.json")
    if not text:
        return found
    try:
        companies = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return found

    if not isinstance(companies, list):
        return found

    # Extract ATS slugs from jobs_url fields directly — no extra HTTP requests needed
    for company in companies:
        jobs_url = company.get("jobs_url") or company.get("url") or ""
        website = company.get("website") or ""
        for url in [jobs_url, website]:
            if not url:
                continue
            for ats, patterns in ATS_PATTERNS.items():
                for pattern in patterns:
                    for m in pattern.findall(url):
                        slug = m.lower().strip().strip("-.")
                        if slug and len(slug) > 1 and not slug.startswith("www"):
                            found.add((ats, slug))

    return found


def harvest_candidates():
    """Pull candidate (ats, slug) pairs from all discovery sources."""
    found = set()

    # 1. Scan all GitHub source repos
    for url in EXTRA_SOURCE_URLS:
        text = fetch_text(url)
        if not text:
            continue
        for ats, patterns in ATS_PATTERNS.items():
            for pattern in patterns:
                for m in pattern.findall(text):
                    slug = m.lower().strip().strip("-.")
                    if slug and len(slug) > 1 and not slug.startswith("www"):
                        found.add((ats, slug))
        time.sleep(0.2)

    # 2. Scan curated company list sources
    for url in CURATED_COMPANY_LIST_URLS:
        text = fetch_text(url)
        if not text:
            continue
        for ats, patterns in ATS_PATTERNS.items():
            for pattern in patterns:
                for m in pattern.findall(text):
                    slug = m.lower().strip().strip("-.")
                    if slug and len(slug) > 1 and not slug.startswith("www"):
                        found.add((ats, slug))
        time.sleep(0.2)

    # 3. CareerPuck has its own enumerable sitemap — use it directly.
    found |= harvest_careerpuck_sitemap()

    # 4. Y Combinator company list — direct ATS link extraction
    found |= harvest_yc_companies()

    return found


def validate_candidate(ats, slug):
    """
    Returns the number of jobs the board currently exposes.
    0 means invalid / dead / empty -> do NOT persist.
    """
    fetcher = FETCHERS.get(ats)
    if not fetcher:
        return 0
    try:
        jobs = fetcher(slug)
        return len(jobs)
    except Exception:
        return 0


def run_discovery(verbose=True):
    """
    Main discovery routine. Conservative: validates before persisting.

    Steps:
      1. Load existing companies + pending candidates.
      2. Harvest fresh candidate slugs from sources.
      3. For each *new* candidate (not already a known company), validate it
         in parallel (20 workers).
         - If it returns jobs -> promote to companies.json (source=discovered).
         - If not -> keep it in the candidates file with an attempt count;
           drop it after 5 failed validation attempts so we stop retrying junk.
    """
    if verbose:
        print("=== Auto-discovery ===")

    companies = load_companies()
    known = {(c["ats"], c["slug"]) for c in companies}
    candidates = load_candidates()

    harvested = harvest_candidates()
    new_harvested = [pair for pair in harvested if pair not in known]

    if verbose:
        print(f"Harvested {len(harvested)} slugs from sources, "
              f"{len(new_harvested)} not already known")

    # Cap validations per run to avoid runaway runtimes.
    # deep mode: nightly workflow sweeps the full backlog.
    MAX_VALIDATIONS = 60 if DISCOVERY_MODE == "conservative" else (2000 if DISCOVERY_MODE == "deep" else 500)
    PARALLEL_WORKERS = 20

    to_validate = new_harvested[:MAX_VALIDATIONS]
    # Stash the rest as pending for next run
    for ats, slug in new_harvested[MAX_VALIDATIONS:]:
        key = f"{ats}|{slug}"
        if key not in candidates:
            candidates[key] = {"ats": ats, "slug": slug, "attempts": 0,
                               "first_seen": _now()}

    promoted = 0
    rejected = 0

    if verbose:
        print(f"Validating {len(to_validate)} candidates with {PARALLEL_WORKERS} workers...")

    def _validate(pair):
        ats, slug = pair
        count = validate_candidate(ats, slug)
        return ats, slug, count

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        futures = {pool.submit(_validate, pair): pair for pair in to_validate}
        for future in as_completed(futures):
            try:
                ats, slug, job_count = future.result()
            except Exception:
                continue

            key = f"{ats}|{slug}"
            if job_count > 0:
                companies.append({
                    "slug": slug,
                    "ats": ats,
                    "source": "discovered",
                    "added_at": _now(),
                    "last_validated_at": _now(),
                    "miss_streak": 0,
                    "last_job_count": job_count,
                })
                known.add((ats, slug))
                candidates.pop(key, None)
                promoted += 1
                if verbose:
                    print(f"  + PROMOTED {ats}:{slug} ({job_count} jobs)")
            else:
                # Track failed attempts; drop after 5 tries (was 3).
                entry = candidates.get(key, {"ats": ats, "slug": slug, "attempts": 0,
                                             "first_seen": _now()})
                entry["attempts"] = entry.get("attempts", 0) + 1
                if entry["attempts"] >= 5:
                    candidates.pop(key, None)
                    rejected += 1
                else:
                    candidates[key] = entry

    save_companies(companies)
    save_candidates(candidates)

    if verbose:
        print(f"\nDiscovery summary:")
        print(f"  Promoted to companies.json: {promoted}")
        print(f"  Rejected (5 failed tries):  {rejected}")
        print(f"  Pending candidates:         {len(candidates)}")
        print(f"  Total companies now:        {len(companies)}")

    return promoted


def prune_dead_boards(verbose=True):
    """
    Increment miss_streak for boards that returned no jobs in the latest fetch,
    reset it for those that did, and remove boards exceeding the max miss streak.

    This is called by fetch.py after a run, passing in the per-board job counts.
    Here we provide the standalone version that re-checks; fetch.py uses the
    integrated update_board_health() below to avoid double-fetching.
    """
    pass  # Integrated into fetch via update_board_health (below)


def update_board_health(job_counts_by_board, verbose=True):
    """
    Called by fetch.py after a normal run.

    job_counts_by_board: dict of (ats, slug) -> job_count from this run.

    - Boards with jobs: reset miss_streak, update last_validated_at + count.
    - Boards with 0 jobs: increment miss_streak.
    - Boards over DISCOVERY_MAX_MISS_STREAK: pruned (but only 'discovered' and
      'simplify' sources; curated seeds are kept even if temporarily empty,
      since they're hand-verified and may just have no current openings).
    """
    companies = load_companies()
    pruned = []
    kept = []

    for c in companies:
        key = (c["ats"], c["slug"])
        count = job_counts_by_board.get(key, 0)

        if count > 0:
            c["miss_streak"] = 0
            c["last_validated_at"] = _now()
            c["last_job_count"] = count
        else:
            c["miss_streak"] = c.get("miss_streak", 0) + 1
            c["last_job_count"] = 0

        # Prune only non-curated boards that have been dead too long.
        if (c.get("source") in ("discovered", "simplify")
                and c.get("miss_streak", 0) > DISCOVERY_MAX_MISS_STREAK):
            pruned.append(c)
        else:
            kept.append(c)

    save_companies(kept)

    if verbose and pruned:
        print(f"\nPruned {len(pruned)} dead boards "
              f"(>{DISCOVERY_MAX_MISS_STREAK} consecutive empty runs):")
        for c in pruned[:10]:
            print(f"  - {c['ats']}:{c['slug']} (source={c.get('source')})")
        if len(pruned) > 10:
            print(f"  ... and {len(pruned) - 10} more")

    return len(pruned)


if __name__ == "__main__":
    run_discovery()
