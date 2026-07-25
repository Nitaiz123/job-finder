"""
ATS clients. Each returns a list of normalized job dicts:
{
    "company": str,
    "ats": str,
    "title": str,
    "location": str,
    "url": str,
    "posted_at": str (ISO),
    "department": str,
    "description_snippet": str,  # first ~500 chars for hashing
}

API references:
  Greenhouse: https://developers.greenhouse.io/job-board.html [documented]
    GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
  Lever: https://help.lever.co/hc/en-us/articles/360044738111 [documented]
    GET https://api.lever.co/v0/postings/{slug}?mode=json
  Ashby: public job board JSON API [documented]
    GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
  Workable: public widget API [documented]
    GET https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true
  Workday: undocumented but stable [used by their own frontend]
    POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
  Eightfold: undocumented but stable [used by their own frontend]
    GET https://{company}.eightfold.ai/api/apply/v2/jobs?...
"""

import html
import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from config import REQUEST_TIMEOUT, USER_AGENT

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# iCIMS pages are HTML, not JSON — use a browser-like Accept header for them.
HTML_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _strip_html(html):
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_iso(s):
    """Return ISO 8601 string or empty. Accepts varied input."""
    if not s:
        return ""
    try:
        # Common formats from these APIs
        if isinstance(s, (int, float)):
            return datetime.fromtimestamp(s / 1000 if s > 1e10 else s, tz=timezone.utc).isoformat()
        s = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return str(s)


def fetch_greenhouse(slug):
    """Greenhouse public job board API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    jobs = []
    for j in data.get("jobs", []):
        desc = _strip_html(j.get("content", ""))
        location = (j.get("location") or {}).get("name", "")
        departments = ", ".join(d.get("name", "") for d in j.get("departments", []))
        jobs.append({
            "company": slug,
            "ats": "greenhouse",
            "title": j.get("title", ""),
            "location": location,
            "url": j.get("absolute_url", ""),
            "posted_at": _parse_iso(j.get("updated_at") or j.get("first_published")),
            "department": departments,
            "description_snippet": desc[:500],
            "description_full": desc,
        })
    return jobs


def fetch_lever(slug):
    """Lever public postings API."""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    if not isinstance(data, list):
        return []

    jobs = []
    for j in data:
        categories = j.get("categories", {}) or {}
        location = categories.get("location", "") or categories.get("allLocations", [""])[0] \
            if categories.get("allLocations") else categories.get("location", "")
        desc = _strip_html(j.get("descriptionPlain") or j.get("description", ""))
        jobs.append({
            "company": slug,
            "ats": "lever",
            "title": j.get("text", ""),
            "location": location or "",
            "url": j.get("hostedUrl") or j.get("applyUrl", ""),
            "posted_at": _parse_iso(j.get("createdAt")),
            "department": categories.get("department", "") or categories.get("team", ""),
            "description_snippet": desc[:500],
            "description_full": desc,
        })
    return jobs


def fetch_ashby(slug):
    """Ashby public job board API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    jobs = []
    for j in data.get("jobs", []):
        desc = _strip_html(j.get("descriptionHtml") or j.get("descriptionPlain", ""))
        jobs.append({
            "company": slug,
            "ats": "ashby",
            "title": j.get("title", ""),
            "location": j.get("location", "") or j.get("locationName", ""),
            "url": j.get("jobUrl") or j.get("applyUrl", ""),
            "posted_at": _parse_iso(j.get("publishedAt") or j.get("updatedAt")),
            "department": j.get("department", "") or j.get("team", ""),
            "description_snippet": desc[:500],
            "description_full": desc,
        })
    return jobs


def fetch_workable(slug):
    """Workable public widget API."""
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    jobs = []
    for j in data.get("jobs", []):
        loc = j.get("location", {}) or {}
        location_str = ", ".join(filter(None, [
            loc.get("city", ""), loc.get("region", ""), loc.get("country", "")
        ]))
        desc = _strip_html(j.get("description", ""))
        # Workable URL format
        shortcode = j.get("shortcode", "")
        url_out = f"https://apply.workable.com/{slug}/j/{shortcode}/" if shortcode else ""
        jobs.append({
            "company": slug,
            "ats": "workable",
            "title": j.get("title", ""),
            "location": location_str,
            "url": url_out,
            "posted_at": _parse_iso(j.get("published_on") or j.get("created_at")),
            "department": j.get("department", "") or "",
            "description_snippet": desc[:500],
            "description_full": desc,
        })
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
}


def fetch_workday(slug):
    """
    Workday undocumented careers JSON API.

    The 'slug' for Workday is a compound: 'tenant|host|site' (optionally
    'tenant|host|site|locale'). Defaults locale to 'en-US'.
      tenant = company tenant id (e.g. 'nvidia', 'salesforce')
      host   = the wd<N> subdomain (e.g. 'wd5', 'wd1')
      site   = the external site path (e.g. 'NVIDIAExternalCareerSite')
      locale = optional, default 'en-US' (some EU tenants use 'en-GB' etc.)

    Endpoint:
      POST https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

    Public listing URL (this is what gets shown to the user — the bug we just
    fixed was that we were building this without the /{locale}/{site} prefix,
    which pointed at the API path, not the candidate-facing page):
      https://{tenant}.{host}.myworkdayjobs.com/{locale}/{site}{externalPath}

    Some large tenants (Shell, Goldman Sachs, etc.) use protected Workday
    instances that require a browser session. Those return 401/403/422 here
    and the run continues gracefully.

    Returns up to ~5 pages (100 jobs) per company to keep things fast.
    """
    parts = slug.split("|")
    if len(parts) == 3:
        tenant, host, site = parts
        locale = "en-US"
    elif len(parts) == 4:
        tenant, host, site, locale = parts
    else:
        return []

    api_url = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    public_base = f"https://{tenant}.{host}.myworkdayjobs.com/{locale}/{site}"

    jobs_out = []
    headers = dict(HEADERS)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"
    # Referer matters: it makes the request look like it's coming from the
    # candidate frontend, which reduces the rate of soft-blocks on some tenants.
    headers["Referer"] = public_base

    PAGE_SIZE = 20
    # No page cap — paginate until Workday returns empty page

    page = 0
    import time as _time
    _deadline = _time.time() + 300  # max 5 min per Workday tenant
    while True:  # paginate until empty page or time limit
        if _time.time() > _deadline:
            break
        payload = {"limit": PAGE_SIZE, "offset": page * PAGE_SIZE,
                   "searchText": "", "appliedFacets": {}}
        try:
            r = requests.post(api_url, headers=headers, json=payload,
                              timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                break
            data = r.json()
        except (requests.RequestException, ValueError):
            break

        postings = data.get("jobPostings", [])
        if not postings:
            break

        for j in postings:
            external_path = j.get("externalPath", "")
            # external_path is like '/job/Santa-Clara-CA/Senior-Software-Engineer_R-12345'
            # The public URL needs the /{locale}/{site} prefix.
            job_url = f"{public_base}{external_path}" if external_path else ""

            # Workday's `postedOn` is often a relative string. Best-effort parse.
            posted_raw = j.get("postedOn", "")
            posted_iso = _workday_posted_to_iso(posted_raw)

            jobs_out.append({
                "company": tenant,
                "ats": "workday",
                "title": j.get("title", ""),
                "location": j.get("locationsText", "") or "",
                "url": job_url,
                "posted_at": posted_iso,
                "department": "",  # Workday doesn't expose this in the list response
                "description_snippet": "",  # Would require a per-job detail fetch; skip for speed
                "description_full": "",  # See note above; full JD not in list endpoint
            })

        # If we got fewer than a full page, we're done
        if len(postings) < PAGE_SIZE:
            break
        page += 1

    return jobs_out


def _workday_posted_to_iso(raw):
    """
    Workday returns 'postedOn' as a string like:
      'Posted Today', 'Posted Yesterday', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'
    Map those to approximate timestamps so the freshness filter works.
    Some tenants return an actual ISO date — handle that too.
    """
    if not raw:
        return ""
    raw_lower = raw.lower().strip()
    now = datetime.now(timezone.utc)

    if "today" in raw_lower:
        return now.isoformat()
    if "yesterday" in raw_lower:
        return (now - timedelta(days=1)).isoformat()

    # "Posted N Days Ago" / "Posted N+ Days Ago"
    m = re.search(r"(\d+)\+?\s*day", raw_lower)
    if m:
        days = int(m.group(1))
        return (now - timedelta(days=days)).isoformat()

    # Maybe it's an ISO date
    return _parse_iso(raw)


def fetch_eightfold(slug):
    """
    Eightfold AI undocumented careers JSON API.

    Endpoint:
      GET https://{slug}.eightfold.ai/api/apply/v2/jobs?domain={slug}.com&start=0&num=50&...
    Note: the 'domain' parameter is required and is typically the company's own domain.
    We fall back to '{slug}.com' which works for most public tenants.
    """
    base = f"https://{slug}.eightfold.ai/api/apply/v2/jobs"
    jobs_out = []

    MAX_PAGES = 4
    PAGE_SIZE = 50

    for page in range(MAX_PAGES):
        params = {
            "domain": f"{slug}.com",
            "start": page * PAGE_SIZE,
            "num": PAGE_SIZE,
            "sort_by": "relevance",
        }
        try:
            r = requests.get(base, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                break
            data = r.json()
        except (requests.RequestException, ValueError):
            break

        positions = data.get("positions", [])
        if not positions:
            break

        for j in positions:
            # t_create is unix timestamp in seconds (sometimes ms)
            posted_iso = _parse_iso(j.get("t_create") or j.get("t_update"))

            # Location can be a list of objects or a string
            loc = j.get("locations", []) or []
            if isinstance(loc, list) and loc:
                location_str = ", ".join(str(x) for x in loc if x)
            else:
                location_str = j.get("location", "") or ""

            # Eightfold canonical job URL
            job_id = j.get("id", "")
            job_url = f"https://{slug}.eightfold.ai/careers?pid={job_id}" if job_id else ""

            desc = _strip_html(j.get("job_description", ""))

            jobs_out.append({
                "company": slug,
                "ats": "eightfold",
                "title": j.get("name", "") or j.get("display_job_title", ""),
                "location": location_str,
                "url": job_url,
                "posted_at": posted_iso,
                "department": j.get("department", "") or "",
                "description_snippet": desc[:500],
                "description_full": desc,
            })

        if len(positions) < PAGE_SIZE:
            break

    return jobs_out


FETCHERS["workday"] = fetch_workday
FETCHERS["eightfold"] = fetch_eightfold


def _icims_base(slug):
    """
    iCIMS tenants live at either:
      https://careers-{slug}.icims.com
      https://{slug}.icims.com
    The 'slug' may already encode which one via a 'careers-' prefix convention.
    We try the careers- form first (most common), then the bare form.
    """
    if slug.startswith("careers-"):
        return [f"https://{slug}.icims.com"]
    return [f"https://careers-{slug}.icims.com", f"https://{slug}.icims.com"]


def fetch_icims(slug):
    """
    iCIMS career portal — best-effort HTML scrape.

    iCIMS does not expose a clean cross-tenant JSON API. Most tenants render
    a server-side job-search page at:
      {base}/jobs/search?ss=1&pr={page}

    We parse job rows out of the HTML. iCIMS markup has shifted across versions,
    so we try several selectors. Many tenants require JS rendering or gate
    search behind tokens — for those, this returns [] and the run continues.

    Limitations (by design — see README):
      - posted_at is usually NOT in the list view -> freshness filter will
        drop these unless we leave it blank. We set posted_at = "" and the
        fetch layer's is_fresh() returns False for empty, so iCIMS jobs would
        normally be filtered out. To avoid silently dropping ALL iCIMS jobs,
        we stamp them with the current time (treat "appeared in search now" as
        the freshness signal). This is a deliberate, documented compromise.
      - description_full requires a second request per job; we skip it for
        speed and set it empty (rows show "no JD" in the dashboard).
    """
    if not _HAS_BS4:
        return []

    jobs_out = []
    seen_urls = set()
    MAX_PAGES = 4

    for base in _icims_base(slug):
        got_any_for_this_base = False

        for page in range(MAX_PAGES):
            url = f"{base}/jobs/search?ss=1&pr={page}&in_iframe=1"
            try:
                r = requests.get(url, headers=HTML_HEADERS, timeout=REQUEST_TIMEOUT)
            except requests.RequestException:
                break
            if r.status_code != 200 or not r.text:
                break

            page_jobs = _parse_icims_html(r.text, base, slug)
            if not page_jobs:
                break

            new_on_page = 0
            for job in page_jobs:
                if job["url"] in seen_urls:
                    continue
                seen_urls.add(job["url"])
                jobs_out.append(job)
                new_on_page += 1

            got_any_for_this_base = True
            # If a page yielded no *new* rows, pagination has looped — stop.
            if new_on_page == 0:
                break

        # If the careers- form worked, don't also try the bare form.
        if got_any_for_this_base:
            break

    return jobs_out


def _parse_icims_html(html, base, slug):
    """
    Extract job rows from an iCIMS search page. Tries multiple selector
    strategies because iCIMS markup varies by tenant/version.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    # Strategy 1: explicit job-listing rows (newer iCIMS).
    candidates = soup.select(".iCIMS_JobsTable .row, .iCIMS_JobListingRow, "
                             "div[class*='JobListingRow']")

    # Strategy 2: anchor-based (older iCIMS / some tenants).
    anchors = soup.select("a.iCIMS_Anchor[href*='/jobs/'], a[href*='/jobs/'][title]")

    def make_job(title, href, location):
        if not title or not href:
            return None
        # Resolve relative URLs.
        if href.startswith("/"):
            href = base + href
        elif not href.startswith("http"):
            href = base + "/" + href
        return {
            "company": slug.replace("careers-", ""),
            "ats": "icims",
            "title": title.strip(),
            "location": (location or "").strip(),
            "url": href,
            # See docstring: iCIMS list view lacks posted dates, so we stamp
            # "now" as a freshness proxy. Documented compromise.
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "department": "",
            "description_snippet": "",
            "description_full": "",
        }

    # Prefer structured rows when present.
    for row in candidates:
        link = row.select_one("a[href*='/jobs/']")
        if not link:
            continue
        title = link.get_text(strip=True) or link.get("title", "")
        href = link.get("href", "")
        loc_el = row.select_one("[class*='location'], [class*='Location']")
        location = loc_el.get_text(strip=True) if loc_el else ""
        job = make_job(title, href, location)
        if job:
            rows.append(job)

    # Fall back to anchors only if structured rows found nothing.
    if not rows:
        for a in anchors:
            title = a.get_text(strip=True) or a.get("title", "")
            href = a.get("href", "")
            # Skip obvious non-job links.
            if not title or "/jobs/search" in href or "login" in href.lower():
                continue
            job = make_job(title, href, "")
            if job:
                rows.append(job)

    return rows


FETCHERS["icims"] = fetch_icims


def fetch_careerpuck(slug):
    """
    CareerPuck public JSON API.

    Endpoint:
      GET https://api.careerpuck.com/v1/public/job-boards/{slug}
    Requires Origin/Referer headers or it may reject the request.
    Returns all active jobs with full descriptions in one request (no pagination).

    Note: CareerPuck often proxies other ATSes (Greenhouse, Lever, ...). The
    'atsSourcePlatform' field records the underlying ATS. Such jobs may also
    appear via those direct fetchers; the dedupe layer handles overlaps.
    """
    url = f"https://api.careerpuck.com/v1/public/job-boards/{slug}"
    headers = {
        "Accept": "*/*",
        "User-Agent": USER_AGENT,
        "Origin": "https://app.careerpuck.com",
        "Referer": "https://app.careerpuck.com/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    jobs_out = []
    for j in data.get("jobs", []):
        # The content field is HTML-encoded; unescape, then strip tags.
        raw_content = html.unescape(j.get("content", "") or "")
        desc = _strip_html(raw_content)

        # workplaceType (remote/hybrid/onsite) enriches the location string,
        # which helps the region classifier.
        location = j.get("location", "") or ""
        workplace = j.get("workplaceType", "") or ""
        if workplace and workplace.lower() not in location.lower():
            location = f"{location} ({workplace})".strip()

        jobs_out.append({
            "company": slug,
            "ats": "careerpuck",
            "title": j.get("title", ""),
            "location": location,
            "url": j.get("publicUrl") or j.get("applyUrl", ""),
            "posted_at": _parse_iso(j.get("postedAt")),
            "department": j.get("department", "") or j.get("team", ""),
            "description_snippet": desc[:500],
            "description_full": desc,
            # CareerPuck-specific: which ATS this job actually originates from.
            "source_platform": j.get("atsSourcePlatform", "") or "",
        })
    return jobs_out


FETCHERS["careerpuck"] = fetch_careerpuck


def fetch_smartrecruiters(slug):
    """
    SmartRecruiters public job search API.

    Endpoint:
      GET https://api.smartrecruiters.com/v1/companies/{slug}/postings
    Fully documented, no auth required for public postings.
    """
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    params = {"limit": 100, "offset": 0}
    jobs_out = []

    page = 0
    import time as _time
    _deadline = _time.time() + 300  # max 5 min per company
    while True:  # paginate until SmartRecruiters returns empty page or time limit
        if _time.time() > _deadline:
            break
        params["offset"] = page * 100
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                break
            data = r.json()
        except (requests.RequestException, ValueError):
            break

        postings = data.get("content", [])
        if not postings:
            break

        for j in postings:
            loc = j.get("location", {}) or {}
            location_parts = [loc.get("city", ""), loc.get("region", ""), loc.get("country", "")]
            location_str = ", ".join(p for p in location_parts if p)
            if j.get("location", {}).get("remote"):
                location_str = ("Remote, " + location_str).strip(", ")

            job_id = j.get("id", "")
            job_url = f"https://jobs.smartrecruiters.com/{slug}/{job_id}" if job_id else ""

            jobs_out.append({
                "company": slug,
                "ats": "smartrecruiters",
                "title": j.get("name", ""),
                "location": location_str,
                "url": job_url,
                "posted_at": _parse_iso(j.get("releasedDate") or j.get("updatedOn")),
                "department": (j.get("department") or {}).get("label", ""),
                "description_snippet": "",
                "description_full": "",
            })

        if len(postings) < 100:
            break
        page += 1

    return jobs_out


def fetch_jobvite(slug):
    """
    Jobvite public job feed API.

    Endpoint:
      GET https://jobs.jobvite.com/api/company/{slug}/jobs
    Returns JSON array of all open jobs.
    """
    url = f"https://jobs.jobvite.com/api/company/{slug}/jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    jobs_out = []
    for j in data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else []):
        desc = _strip_html(j.get("description", ""))
        jobs_out.append({
            "company": slug,
            "ats": "jobvite",
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("applyUrl") or j.get("url", ""),
            "posted_at": _parse_iso(j.get("date") or j.get("datePosted")),
            "department": j.get("category", "") or j.get("department", ""),
            "description_snippet": desc[:500],
            "description_full": desc,
        })
    return jobs_out


def fetch_rippling(slug):
    """
    Rippling ATS public job board API.

    Endpoint:
      GET https://ats.rippling.com/api/v1/board/{slug}/jobs

    Returns a JSON array of job objects with keys:
      uuid, name, department, url, workLocation
    """
    url = f"https://ats.rippling.com/api/v1/board/{slug}/jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    if not isinstance(data, list):
        return []

    jobs_out = []
    for j in data:
        job_id = j.get("uuid", "")
        job_url = j.get("url") or (
            f"https://ats.rippling.com/{slug}/jobs/{job_id}" if job_id else ""
        )
        loc = j.get("workLocation", {})
        if isinstance(loc, dict):
            loc = loc.get("label", "")
        dept = j.get("department", {})
        if isinstance(dept, dict):
            dept = dept.get("label", "")
        jobs_out.append({
            "company": slug,
            "ats": "rippling",
            "title": j.get("name", ""),
            "location": str(loc or ""),
            "url": job_url,
            "posted_at": None,
            "department": str(dept or ""),
            "description_snippet": "",
            "description_full": "",
        })
    return jobs_out


def fetch_bamboohr(slug):
    """
    BambooHR public careers JSON API.

    Endpoint:
      GET https://{slug}.bamboohr.com/careers/list

    Returns a JSON object with a 'result' array of job objects.
    """
    url = f"https://{slug}.bamboohr.com/careers/list"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        ct = r.headers.get("content-type", "")
        text = r.text.strip()
        if "json" not in ct and not (text.startswith("{") or text.startswith("[")):
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    postings = data.get("result", [])
    if not isinstance(postings, list):
        return []

    jobs_out = []
    for j in postings:
        job_id = j.get("id", "")
        job_url = j.get("url") or (
            f"https://{slug}.bamboohr.com/careers/{job_id}" if job_id else ""
        )
        loc = j.get("location", {}) or {}
        if isinstance(loc, dict):
            city = loc.get("city", "")
            state = loc.get("state", "")
            country = loc.get("country", "")
            loc = ", ".join(p for p in [city, state, country] if p)
        dept = j.get("department", {}) or {}
        if isinstance(dept, dict):
            dept = dept.get("label", "")
        desc = _strip_html(j.get("description", "") or "")
        title = j.get("jobOpeningName") or j.get("title", "")
        if isinstance(title, dict):
            title = title.get("label", "")
        dept = j.get("departmentLabel") or j.get("department", "")
        if isinstance(dept, dict):
            dept = dept.get("label", "")
        jobs_out.append({
            "company": slug,
            "ats": "bamboohr",
            "title": str(title or ""),
            "location": str(loc or ""),
            "url": job_url,
            "posted_at": _parse_iso(j.get("datePosted") or j.get("updatedDate")),
            "department": str(dept or ""),
            "description_snippet": desc[:500],
            "description_full": desc,
        })
    return jobs_out


FETCHERS["smartrecruiters"] = fetch_smartrecruiters
FETCHERS["jobvite"] = fetch_jobvite
FETCHERS["rippling"] = fetch_rippling
FETCHERS["bamboohr"] = fetch_bamboohr


def fetch_amazon(slug="amazon"):
    """
    Amazon Jobs public search API.

    Amazon runs its own ATS at amazon.jobs. The search endpoint returns JSON
    with no authentication required.

    Endpoint:
      GET https://www.amazon.jobs/en/search.json?base_query=&result_limit=10&offset=N

    Fetches up to 20 pages (200 jobs) of the most recent postings.
    The slug parameter is ignored (there is only one Amazon jobs board);
    it exists for interface consistency.
    """
    BASE = "https://www.amazon.jobs/en/search.json"
    LIMIT = 10
    jobs_out = []

    h = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Search for software/engineering roles specifically
    SWE_QUERY = "software engineer OR developer OR SDE OR machine learning OR data engineer OR devops OR cloud engineer OR security engineer OR mobile engineer OR iOS OR android OR platform engineer OR site reliability OR SRE"

    page = 0
    import time as _time
    _deadline = _time.time() + 300  # max 5 min for Amazon
    while True:  # paginate until API returns empty page or time limit
        if _time.time() > _deadline:
            break
        params = {
            "base_query": SWE_QUERY,
            "loc_query": "",
            "result_limit": LIMIT,
            "offset": page * LIMIT,
            "sort": "recent",
        }
        try:
            r = requests.get(BASE, headers=h, params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                break
            data = r.json()
        except (requests.RequestException, ValueError):
            break

        jobs = data.get("jobs", [])
        if not jobs:
            break

        for j in jobs:
            job_path = j.get("job_path", "")
            job_url = f"https://www.amazon.jobs{job_path}" if job_path else ""
            # Amazon's posted_date is a human string like "September 24, 2025"
            posted_raw = j.get("posted_date", "")
            try:
                from datetime import datetime
                posted_iso = datetime.strptime(posted_raw, "%B %d, %Y").replace(
                    tzinfo=__import__('datetime').timezone.utc).isoformat() if posted_raw else ""
            except (ValueError, AttributeError):
                posted_iso = posted_raw

            desc = _strip_html(j.get("description", "") or j.get("description_short", ""))
            jobs_out.append({
                "company": "amazon",
                "ats": "amazon",
                "title": j.get("title", ""),
                "location": j.get("location", ""),
                "url": job_url,
                "posted_at": posted_iso,
                "department": j.get("job_category", "") or j.get("category", ""),
                "description_snippet": desc[:500],
                "description_full": desc,
            })

        if len(jobs) < LIMIT:
            break
        page += 1

    return jobs_out


def fetch_apple(slug="apple"):
    """
    Apple Jobs scraper using server-side hydration data.

    Apple's careers site (jobs.apple.com) renders job listings server-side
    and embeds them in a React Router hydration blob:
      window.__staticRouterHydrationData = JSON.parse("...");

    Each page returns 20 jobs. We paginate up to MAX_PAGES.
    The slug parameter is ignored (single Apple board); exists for consistency.
    """
    # Apple's careers site uses server-side React Router hydration data.
    # The search page embeds all job data as a JSON-encoded string in:
    #   window.__staticRouterHydrationData = JSON.parse("...");
    # We decode it with json.loads('"' + raw + '"') to handle double-escaping.
    BASE = "https://jobs.apple.com/en-us/search"
    # Filter for software engineering roles
    QUERY = "software engineer"
    jobs_out = []

    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    page = 1
    import time as _time
    _deadline = _time.time() + 300  # max 5 min for Apple
    while True:  # paginate until Apple returns empty/short page or time limit
        if _time.time() > _deadline:
            break
        # Use relevance sort so SWE roles appear before retail/operations jobs
        url = f"{BASE}?q={requests.utils.quote(QUERY)}&sort=relevance&page={page}"
        try:
            r = requests.get(url, headers=h, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                break
            text = r.text
        except requests.RequestException:
            break

        # Extract the hydration blob
        m = re.search(
            r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.+?)"\);\s*</script>',
            text, re.DOTALL
        )
        if not m:
            break

        raw = m.group(1)
        try:
            # The raw string is double-JSON-encoded; wrap in quotes so json.loads
            # handles all escape sequences correctly.
            decoded_str = json.loads('"' + raw + '"')
            data = json.loads(decoded_str)
        except Exception:
            break

        search_data = data.get('loaderData', {}).get('search', {})
        results = search_data.get('searchResults', [])
        if not results:
            break

        for j in results:
            locs = j.get('locations', []) or []
            location_str = '; '.join(
                ', '.join(filter(None, [
                    l.get('city', ''), l.get('stateProvince', ''),
                    l.get('countryName', '') or l.get('countryCode', '')
                ]))
                for l in locs
            ) if locs else ''

            pos_id = j.get('positionId', '')
            job_url = f"https://jobs.apple.com/en-us/details/{pos_id}" if pos_id else ''
            desc = _strip_html(j.get('jobSummary', '') or '')

            posted_raw = (j.get('postDateInGMT') or j.get('postingDate') or '')

            jobs_out.append({
                "company": "apple",
                "ats": "apple",
                "title": j.get('postingTitle', '') or j.get('title', ''),
                "location": location_str,
                "url": job_url,
                "posted_at": _parse_iso(posted_raw),
                "department": j.get('team', '') or '',
                "description_snippet": desc[:500],
                "description_full": desc,
            })

        # If fewer than 20 results, we've reached the last page
        if len(results) < 20:
            break
        page += 1

    return jobs_out


FETCHERS["amazon"] = fetch_amazon
FETCHERS["apple"] = fetch_apple


def fetch_google(slug="google"):
    """
    Google Careers scraper using the internal batchexecute RPC API.

    Google's careers site uses a Google-internal RPC framework (batchexecute)
    with RPC method ``r06xKb`` for job search. The endpoint is:
      POST https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute

    The request requires specific browser-fingerprint headers captured from a
    real browser session (x-browser-validation, x-browser-year, bl build label).
    These are stable across sessions as long as the build label is current.

    Response format: )]}'\nSIZE\n[["wrb.fr","r06xKb","JSON_STRING",...]]\n...
    The inner JSON is a list: [job_list, None, total_count]
    Each job entry is a list with fields at fixed indices:
      [0]  job_id (str)
      [1]  title (str)
      [2]  apply_url (str, signin redirect)
      [3]  responsibilities HTML (list: [None, html])
      [4]  qualifications HTML (list: [None, html])
      [9]  locations (list of [city_str, [addr], city, zip, state, country])
      [10] overview HTML (list: [None, html])
      [12] posted_at timestamp (list: [seconds, nanoseconds])
    """
    BASE_URL = (
        "https://www.google.com/about/careers/applications/"
        "_/HiringCportalFrontendUi/data/batchexecute"
    )
    # Build label from HAR — changes with Google deployments (~weekly)
    # but the validation token is tied to this specific bl value.
    BL = "boq_corp-hiring-boq-cportal-frontend_20260527.06_p0"
    VALIDATION = "DFscXLDsHH1VQnRCDDL79rC1sbU="
    # No page cap — paginate until Google returns empty page

    h = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.7778.179 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.google.com",
        "Referer": "https://www.google.com/",
        "X-Same-Domain": "1",
        "X-Browser-Channel": "stable",
        "X-Browser-Copyright": "Copyright 2026 Google LLC. All Rights Reserved.",
        "X-Browser-Validation": VALIDATION,
        "X-Browser-Year": "2026",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "DNT": "1",
    }

    jobs_out = []
    page = 1
    import time as _time
    _deadline = _time.time() + 300  # max 5 min for Google
    while True:  # paginate until Google returns empty page or time limit
        if _time.time() > _deadline:
            break
        # Build the inner RPC payload
        inner = (
            '[[null,null,null,null,"en-US",null,null,' + str(page) + ']]'
        )
        freq = json.dumps([[['r06xKb', inner, None, '3']]])
        body = urllib.parse.urlencode({'f.req': freq, '': ''})

        params = {
            'rpcids': 'r06xKb',
            'source-path': '/about/careers/applications/jobs/results',
            'f.sid': '-389101631705574599',
            'bl': BL,
            'hl': 'en-US',
            'soc-app': '1',
            'soc-platform': '1',
            'soc-device': '1',
            '_reqid': str(1000000 + page * 100),
            'rt': 'c',
        }

        try:
            r = requests.post(
                BASE_URL, params=params, headers=h, data=body,
                timeout=REQUEST_TIMEOUT
            )
            if r.status_code != 200:
                break
            raw = r.text
        except requests.RequestException:
            break

        # Parse the batchexecute response
        jobs_data = None
        for line in raw.split('\n'):
            line = line.strip()
            if line.startswith('["wrb.fr","r06xKb"') or line.startswith('[["wrb.fr","r06xKb"'):
                try:
                    outer = json.loads(line)
                    # Handle both [[...]] and [...] wrapping
                    if isinstance(outer[0], list):
                        inner_json = outer[0][2]
                    else:
                        inner_json = outer[2]
                    if inner_json:
                        jobs_data = json.loads(inner_json)
                except (json.JSONDecodeError, IndexError, TypeError):
                    pass
                break

        if not jobs_data or not isinstance(jobs_data, list) or not jobs_data[0]:
            break

        job_list = jobs_data[0]
        for job_entry in job_list:
            if not isinstance(job_entry, list) or len(job_entry) < 3:
                continue

            job_id = job_entry[0] or ''
            title = job_entry[1] or ''
            apply_url = job_entry[2] or ''

            # Build a stable direct URL from job_id
            job_url = (
                f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"
                if job_id else apply_url
            )

            # Location: field [9] is a list of location tuples
            location = ''
            if len(job_entry) > 9 and isinstance(job_entry[9], list):
                locs = job_entry[9]
                parts = []
                for loc in locs:
                    if isinstance(loc, list) and loc:
                        city = loc[2] if len(loc) > 2 and loc[2] else ''
                        state = loc[4] if len(loc) > 4 and loc[4] else ''
                        country = loc[5] if len(loc) > 5 and loc[5] else ''
                        part = ', '.join(filter(None, [city, state, country]))
                        if part:
                            parts.append(part)
                location = '; '.join(parts)

            # Description: combine overview [10], responsibilities [3], qualifications [4]
            def _get_html(entry, idx):
                if len(entry) > idx and isinstance(entry[idx], list) and len(entry[idx]) > 1:
                    return entry[idx][1] or ''
                return ''

            overview_html = _get_html(job_entry, 10)
            resp_html = _get_html(job_entry, 3)
            qual_html = _get_html(job_entry, 4)
            full_html = '\n'.join(filter(None, [overview_html, resp_html, qual_html]))
            desc = _strip_html(full_html)

            # Posted timestamp: field [12] = [seconds, nanoseconds]
            posted_at = ''
            if len(job_entry) > 12 and isinstance(job_entry[12], list) and job_entry[12]:
                ts = job_entry[12][0]
                if ts:
                    try:
                        from datetime import datetime, timezone
                        posted_at = datetime.fromtimestamp(
                            int(ts), tz=timezone.utc
                        ).isoformat()
                    except (ValueError, OSError):
                        pass

            # Department: field [7]
            dept = job_entry[7] if len(job_entry) > 7 and isinstance(job_entry[7], str) else ''

            jobs_out.append({
                'company': 'google',
                'ats': 'google',
                'title': title,
                'location': location,
                'url': job_url,
                'posted_at': posted_at,
                'department': dept,
                'description_snippet': desc[:500],
                'description_full': desc,
            })

        if len(job_list) < 20:
            break
        page += 1

    return jobs_out


def fetch_microsoft(slug="microsoft"):
    """
    Microsoft Careers scraper using the PCSX search API.

    Discovered from HAR analysis of apply.careers.microsoft.com.
    Uses the Eightfold-powered PCSX search endpoint:
      GET https://apply.careers.microsoft.com/api/pcsx/search

    Parameters:
      domain    - microsoft.com
      query     - search term (e.g. 'software engineer')
      location  - optional location filter
      start     - 0-based offset for pagination (10 per page)

    Response structure:
      {
        data: {
          count: N,
          positions: [
            {
              id: int,
              name: str,           # job title
              locations: [str],    # list of location strings
              postedTs: int,       # Unix timestamp
              department: str,
              workLocationOption: str,  # 'onsite'/'hybrid'/'remote'
              positionUrl: str,    # relative URL path
            }, ...
          ]
        }
      }

    The slug parameter is ignored; exists for interface consistency.
    """
    BASE = "https://apply.careers.microsoft.com/api/pcsx/search"
    BASE_URL = "https://apply.careers.microsoft.com"
    PAGE_SIZE = 10
    # No page cap — paginate until Microsoft returns empty page

    h = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://apply.careers.microsoft.com/careers?query=software+engineer",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    jobs_out = []
    page = 0
    import time as _time
    _deadline = _time.time() + 300  # max 5 min for Microsoft
    while True:  # paginate until Microsoft returns empty page or time limit
        if _time.time() > _deadline:
            break
        params = {
            "domain": "microsoft.com",
            "query": "software engineer",
            "location": "",
            "start": page * PAGE_SIZE,
        }
        try:
            r = requests.get(
                BASE, headers=h, params=params, timeout=REQUEST_TIMEOUT
            )
            if r.status_code != 200:
                break
            data = r.json()
        except (requests.RequestException, ValueError):
            break

        positions = data.get("data", {}).get("positions", [])
        if not positions:
            break

        from datetime import datetime, timezone as tz
        for pos in positions:
            title = pos.get("name", "").strip()
            if not title:
                continue

            # Location: use first entry from locations list
            locations = pos.get("locations", []) or []
            location = locations[0] if locations else ""

            # URL
            pos_url = pos.get("positionUrl", "")
            url = BASE_URL + pos_url if pos_url.startswith("/") else pos_url

            # Posted date from Unix timestamp
            posted_ts = pos.get("postedTs", 0)
            posted_at = ""
            if posted_ts:
                try:
                    posted_at = datetime.fromtimestamp(posted_ts, tz=tz.utc).isoformat()
                except (ValueError, OSError):
                    pass

            dept = pos.get("department", "")
            work_option = pos.get("workLocationOption", "")

            jobs_out.append({
                "company": "Microsoft",
                "ats": "microsoft",
                "title": title,
                "location": location,
                "url": url,
                "posted_at": posted_at,
                "department": dept,
                "description_snippet": work_option,
                "description_full": "",
            })

        if len(positions) < PAGE_SIZE:
            break
        page += 1

    return jobs_out


FETCHERS['google'] = fetch_google
FETCHERS['microsoft'] = fetch_microsoft


def fetch_recruitee(slug):
    """
    Recruitee public careers API.

    Endpoint:
      GET https://{slug}.recruitee.com/api/offers/?limit=100

    Returns a JSON object with an 'offers' array. Each offer has:
      title, city, country_code, remote_option, careers_apply_url,
      guid, created_at, department, locations
    """
    url = f"https://{slug}.recruitee.com/api/offers/?limit=100"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    jobs = []
    for j in data.get("offers", []):
        city = j.get("city", "") or ""
        country = j.get("country_code", "") or ""
        remote = j.get("remote_option", "") or ""
        if remote and remote.lower() in ("remote", "fully_remote", "fully remote"):
            location = "Remote"
        elif city and country:
            location = f"{city}, {country}"
        elif city:
            location = city
        elif country:
            location = country
        else:
            location = ""

        if remote and remote.lower() in ("hybrid",) and location:
            location = f"{location} (Hybrid)"

        dept = j.get("department", "") or ""
        if isinstance(dept, list):
            dept = ", ".join(str(d) for d in dept if d)

        jobs.append({
            "company": slug,
            "ats": "recruitee",
            "title": j.get("title", "") or j.get("position", ""),
            "location": location,
            "url": j.get("careers_apply_url", ""),
            "posted_at": _parse_iso(j.get("created_at")),
            "department": dept,
            "description_snippet": "",
            "description_full": "",
        })
    return jobs


FETCHERS['recruitee'] = fetch_recruitee
