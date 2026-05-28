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
import re
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

    MAX_PAGES = 5
    PAGE_SIZE = 20

    for page in range(MAX_PAGES):
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
