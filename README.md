# Fresh SWE Jobs Finder

Pulls software engineering jobs from eight ATSes:
- **Greenhouse, Lever, Ashby, Workable** — documented public APIs
- **CareerPuck** — clean public JSON API (full JDs in one request; auto-discovers all its tenants via sitemap)
- **Workday, Eightfold** — undocumented but stable JSON endpoints used by their own frontends
- **iCIMS** — best-effort HTML scrape (large US enterprise/retail/healthcare/finance employers)

Filters for freshly posted roles (last 48h by default), detects reposts
across runs, and outputs a CSV + local HTML dashboard.

No LinkedIn scraping. No ToS violations on the documented four. Workday
and Eightfold endpoints are not contractually public — they could change.
Treat those as best-effort additional coverage.

## Quick start

```bash
pip install -r requirements.txt

# One-time: bootstrap company list from public sources
python bootstrap.py

# Daily: fetch fresh jobs and build dashboard
python run.py

# Open dashboard
open dashboard.html
```

## Files
- `companies.json` — seed list of companies (v2 schema with health metadata), built by bootstrap and grown by discovery
  - For Workday, `slug` is `tenant|wdN|site` (e.g. `nvidia|wd5|NVIDIAExternalCareerSite`)
  - For Eightfold, `slug` is the subdomain (e.g. `capitalone`)
- `discovery_candidates.json` — pending unvalidated boards (managed automatically)
- `jobs.db` — SQLite cache for repost detection
- `jobs_latest.csv` — most recent fetch (spreadsheet-friendly, no JD text)
- `jobs_latest.json` — most recent fetch with full JD text (feeds the dashboard)
- `dashboard.html` — browsable, filterable dashboard

## Auto-discovery (grows the company list over time)
Every run (if `DISCOVERY_ON_EACH_RUN=True`), the tool:
1. Harvests candidate ATS boards from public GitHub job repos.
2. **Validates** each new candidate — only boards that return real jobs get
   added to `companies.json` (marked `source: discovered`). This is the
   conservative gate: junk and dead boards never get persisted.
3. Tracks board health: any board returning zero jobs for
   `DISCOVERY_MAX_MISS_STREAK` (default 5) consecutive runs gets pruned —
   **except** hand-curated seeds, which are never auto-removed.

Tune in `config.py`: `DISCOVERY_MODE` (conservative/aggressive),
`DISCOVERY_MAX_MISS_STREAK`, `DISCOVERY_ON_EACH_RUN`.

Run discovery standalone: `python discover.py`

## Copy job descriptions
Each row in the dashboard has:
- **Copy JD** — copies the full job description (with a title/company/URL
  header) to your clipboard, ready to paste.
- **View** — opens the full JD in a modal, with its own Copy button and a
  link to the original listing.

Full JD text is stored in `jobs_latest.json`. (Workday and iCIMS are the
exceptions — their list views don't return descriptions, so those rows show
"no JD"; the listing link still works.)

## Workday notes
- Slugs are compound: `tenant|wdN|site` (e.g. `nvidia|wd5|NVIDIAExternalCareerSite`).
  Add `|locale` as an optional 4th part for non-English-US tenants
  (e.g. `acme|wd3|ExternalCareers|en-GB`); default is `en-US`.
- **Listing URLs go to the candidate-facing page** at
  `https://{tenant}.{host}.myworkdayjobs.com/{locale}/{site}{externalPath}`.
  (An earlier version of this file built URLs without the `/{locale}/{site}/`
  prefix, which pointed at the internal API path and 404'd — fixed.)
- Some large tenants (Shell, Goldman Sachs, etc.) use protected Workday
  instances that gate the public API behind a browser session. Those return
  401/403/422 here; the run continues gracefully and they show up with zero
  jobs in the per-board health log.
- No descriptions in the list view — Workday rows show "no JD" in the
  dashboard. The public listing link works for getting the JD in-browser.

## CareerPuck note
CareerPuck is one of the best-behaved sources: a clean public JSON API that
returns full job descriptions in one request, plus a public sitemap that
enumerates every company using it. Discovery harvests that sitemap each run,
so the CareerPuck company list grows automatically with no maintenance.

One thing to know: CareerPuck often *proxies* other ATSes (a job's real origin
is in its `source_platform` field — greenhouse, lever, etc.). Such jobs may
also surface via those direct fetchers; the company+title+JD dedupe usually
collapses the duplicates, but you may occasionally see the same role twice if
the two descriptions differ slightly.

## iCIMS notes (read before relying on it)
iCIMS is the flakiest source by design — it has no clean cross-tenant JSON
API, so the tool scrapes the HTML job-search page. Consequences:
- **Many tenants will return nothing.** Some iCIMS portals render jobs via
  JavaScript or gate search behind tokens; those can't be scraped without a
  headless browser (deliberately not added). The run continues regardless.
- **No posted dates.** iCIMS list views don't expose when a job was posted,
  so each iCIMS job is stamped with the time it was first seen. It will
  appear once, then be deduped on later runs via a company+title hash.
- **No JD text** in the list view (rows show "no JD"; open the listing link).
- The seed list (~187 large US employers) is best-effort; verify/extend by
  visiting a company's careers page and checking for an `*.icims.com` URL.

## Tuning
Edit `config.py` to change:
- `FRESHNESS_HOURS` (default 48)
- `SWE_KEYWORDS` and `EXCLUDE_KEYWORDS`
- `LOCATION_FILTERS` (US-only by default; relevant for OPT)

## Adding more Workday tenants
Workday requires three pieces per company (`tenant|wdN|site`). To add one:
1. Go to the company's careers page in your browser
2. Wait for the redirect to `*.myworkdayjobs.com`
3. The URL looks like `https://{tenant}.{wdN}.myworkdayjobs.com/en-US/{site}/...`
4. Add `tenant|wdN|site` to `companies.json` (or to the curated seed in `bootstrap.py`)

## Why no "applicant count" filter?
None of these ATS APIs expose applicant count. Only LinkedIn does, and they
actively block scraping. Freshness + company breadth is the practical proxy
for low competition.
