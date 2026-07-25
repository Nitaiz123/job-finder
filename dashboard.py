"""
Generate a self-contained dashboard.html from jobs_latest.csv.
Embeds job data as JSON, provides client-side filter and sort.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "jobs_latest.csv"
JSON_PATH = ROOT / "jobs_latest.json"
HTML_PATH = ROOT / "dashboard.html"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fresh SWE Jobs — {generated_at}</title>
<style>
  :root {{
    --bg: #fafaf7;
    --panel: #ffffff;
    --ink: #1a1a1a;
    --muted: #6b6b6b;
    --border: #e5e5e0;
    --accent: #c8553d;
    --accent-bg: #faf0ed;
    --hover: #f5f5f0;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--ink);
    margin: 0;
    padding: 24px;
    line-height: 1.5;
  }}
  header {{
    max-width: 1600px;
    margin: 0 auto 24px;
  }}
  h1 {{
    font-size: 28px;
    margin: 0 0 4px;
    letter-spacing: -0.02em;
  }}
  .meta {{
    color: var(--muted);
    font-size: 14px;
    margin-bottom: 20px;
  }}
  .controls {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    grid-template-rows: auto auto;
    gap: 14px 16px;
    align-items: end;
    margin-bottom: 12px;
  }}
  .control-wide {{
    grid-column: 1 / -1;
  }}
  @media (max-width: 900px) {{
    .controls {{
      grid-template-columns: 1fr 1fr;
    }}
    .control-wide {{
      grid-column: 1 / -1;
    }}
  }}
  @media (max-width: 600px) {{
    .controls {{
      grid-template-columns: 1fr;
    }}
  }}
  .control label {{
    display: block;
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
  }}
  .control input, .control select {{
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
    background: var(--bg);
    font-family: inherit;
  }}
  .control input:focus, .control select:focus {{
    outline: none;
    border-color: var(--accent);
    background: white;
  }}
  .count {{
    font-size: 14px;
    color: var(--muted);
    margin-bottom: 12px;
    max-width: 1600px;
    margin-left: auto;
    margin-right: auto;
  }}
  .count strong {{ color: var(--ink); }}
  .container {{
    max-width: 1600px;
    margin: 0 auto;
    overflow-x: auto;
  }}
  table {{
    width: 100%;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    border-collapse: separate;
    border-spacing: 0;
    overflow: hidden;
  }}
  th {{
    text-align: left;
    padding: 12px 14px;
    background: #f5f5f0;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }}
  th:hover {{ color: var(--ink); }}
  th.sorted-asc::after {{ content: " \\2191"; color: var(--accent); }}
  th.sorted-desc::after {{ content: " \\2193"; color: var(--accent); }}
  td {{
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
    vertical-align: top;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--hover); }}
  .title-link {{
    color: var(--accent);
    text-decoration: none;
    font-weight: 500;
  }}
  .title-link:hover {{ text-decoration: underline; }}
  .ats-badge {{
    display: inline-block;
    padding: 2px 8px;
    font-size: 11px;
    border-radius: 3px;
    background: var(--accent-bg);
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
  }}
  .company {{
    font-weight: 500;
    text-transform: capitalize;
  }}
  .empty {{
    padding: 60px;
    text-align: center;
    color: var(--muted);
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
  }}
  .age {{ font-size: 13px; color: var(--muted); }}
  .age-recent {{ color: #2d8659; font-weight: 500; }}
  .region-badge {{
    display: inline-block;
    padding: 2px 8px;
    font-size: 11px;
    border-radius: 3px;
    background: #eef2f7;
    color: #44607d;
    font-weight: 500;
    white-space: nowrap;
  }}
  .sponsor-flag {{
    display: inline-block;
    margin-left: 6px;
    padding: 1px 6px;
    font-size: 10px;
    border-radius: 3px;
    background: #fdf0e3;
    color: #b6712a;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    vertical-align: middle;
  }}
  .toggle-row {{
    max-width: 1600px;
    margin: 0 auto 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: var(--muted);
  }}
  .toggle-row input {{ width: auto; margin: 0; }}
  .toggle-row label {{ cursor: pointer; user-select: none; }}
  tr.row-sponsor td {{ background: #fdfbf7; }}
  tr.row-sponsor:hover td {{ background: #faf6ee; }}
  .actions {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
    min-width: 0;
  }}
  .btn {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 4px 10px;
    font-size: 12px;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--bg);
    color: var(--ink);
    cursor: pointer;
    font-family: inherit;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .btn-copied {{ background: #e8f5ee; border-color: #2d8659; color: #2d8659; }}
  /* Applied button */
  .btn-apply {{
    border-color: #2d8659;
    color: #2d8659;
  }}
  .btn-apply:hover {{ background: #e8f5ee; }}
  .btn-apply.applied {{
    background: #2d8659;
    border-color: #2d8659;
    color: white;
  }}
  .btn-apply.applied:hover {{
    background: #c0392b;
    border-color: #c0392b;
    color: white;
  }}
  /* no-JD indicator as a small muted pill */
  .no-jd-badge {{
    display: inline-block;
    padding: 3px 8px;
    font-size: 11px;
    border-radius: 4px;
    background: #f0f0eb;
    color: #aaa;
    border: 1px solid #e0e0da;
    white-space: nowrap;
  }}
  .modal-overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    z-index: 100;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }}
  .modal-overlay.open {{ display: flex; }}
  .modal {{
    background: var(--panel);
    border-radius: 10px;
    max-width: 760px;
    width: 100%;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.25);
  }}
  .modal-head {{
    padding: 18px 22px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }}
  .modal-head h2 {{ margin: 0; font-size: 18px; }}
  .modal-head .sub {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
  .modal-body {{
    padding: 22px;
    overflow-y: auto;
    white-space: pre-wrap;
    font-size: 14px;
    line-height: 1.6;
    color: #2a2a2a;
  }}
  .modal-foot {{
    padding: 14px 22px;
    border-top: 1px solid var(--border);
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }}
  .modal-close {{
    background: none;
    border: none;
    font-size: 24px;
    line-height: 1;
    cursor: pointer;
    color: var(--muted);
  }}
  .modal-close:hover {{ color: var(--ink); }}
  .toast {{
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: #1a1a1a;
    color: white;
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 14px;
    opacity: 0;
    transition: opacity 0.2s;
    pointer-events: none;
    z-index: 200;
  }}
  .toast.show {{ opacity: 1; }}
  .exp-badge {{
    display: inline-block;
    padding: 2px 8px;
    font-size: 11px;
    border-radius: 3px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .exp-0-2       {{ background: #e8f5ee; color: #2d8659; }}
  .exp-3-5       {{ background: #eef2f7; color: #44607d; }}
  .exp-5plus     {{ background: #faf0ed; color: #c8553d; }}
  .exp-unspecified {{ background: #f5f5f0; color: #6b6b6b; }}
  .new-flag {{
    display: inline-block;
    margin-left: 6px;
    padding: 1px 6px;
    font-size: 10px;
    border-radius: 3px;
    background: #d4edda;
    color: #155724;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    vertical-align: middle;
  }}
  /* Tabs */
  .tabs {{
    max-width: 1600px;
    margin: 0 auto 16px;
    display: flex;
    gap: 4px;
    border-bottom: 2px solid var(--border);
  }}
  .tab-btn {{
    padding: 8px 20px;
    font-size: 14px;
    font-family: inherit;
    border: none;
    background: none;
    cursor: pointer;
    color: var(--muted);
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    font-weight: 500;
    transition: color 0.15s;
  }}
  .tab-btn:hover {{ color: var(--ink); }}
  .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .tab-badge {{
    display: inline-block;
    background: var(--accent);
    color: white;
    font-size: 10px;
    font-weight: 700;
    border-radius: 10px;
    padding: 1px 6px;
    margin-left: 5px;
    vertical-align: middle;
  }}
  .btn-save {{ color: #888; }}
  .btn-save.saved {{ color: #c8553d; border-color: #c8553d; background: #faf0ed; }}
  #savedPanel {{ display: none; }}
  #savedPanel.active {{ display: block; }}
  #appliedPanel {{ display: none; }}
  #appliedPanel.active {{ display: block; }}
  #allPanel.hidden {{ display: none; }}
  .saved-empty {{
    padding: 60px;
    text-align: center;
    color: var(--muted);
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
  }}
  tr.row-applied td {{ background: #f0faf4; }}
  tr.row-applied:hover td {{ background: #e6f5ec; }}
  .applied-date {{ font-size: 12px; color: #2d8659; font-weight: 500; }}
  /* Responsive table: hide less critical columns on small screens */
  @media (max-width: 900px) {{
    body {{ padding: 12px; }}
    .col-region, .col-ats {{ display: none; }}
    td:nth-child(4), th:nth-child(4) {{ display: none; }}
    td:nth-child(5), th:nth-child(5) {{ display: none; }}
  }}
  @media (max-width: 600px) {{
    body {{ padding: 8px; }}
    td, th {{ padding: 8px 8px; font-size: 13px; }}
    .col-location {{ display: none; }}
    td:nth-child(3), th:nth-child(3) {{ display: none; }}
    .btn {{ padding: 4px 7px; font-size: 11px; }}
    .no-jd-badge {{ font-size: 10px; padding: 2px 6px; }}
    h1 {{ font-size: 22px; }}
  }}
</style>
</head>
<body>
<header class="container">
  <h1>Fresh SWE Jobs</h1>
  <div class="meta">Generated {generated_at} &middot; {total_count} accumulated postings &middot; Greenhouse · Lever · Ashby · Workable · Workday · Eightfold · iCIMS · SmartRecruiters · Jobvite · Google · Amazon · Apple · Microsoft</div>
  <div class="controls">
    <!-- Row 1: Search (full width) -->
    <div class="control control-wide">
      <label>Search title or company</label>
      <input type="text" id="search" placeholder="e.g. backend, stripe, platform, openai">
    </div>
    <!-- Row 2: Filters -->
    <div class="control">
      <label>Posted within</label>
      <select id="ageFilter">
        <option value="24">Last 24 hours</option>
        <option value="48" selected>Last 48 hours</option>
        <option value="168">Past week</option>
        <option value="720">Past month</option>
        <option value="999999">All time</option>
      </select>
    </div>
    <div class="control">
      <label>Experience (years)</label>
      <select id="expFilter">
        <option value="">All levels</option>
        <option value="0-2 years">0–2 years</option>
        <option value="3-5 years">3–5 years</option>
        <option value="5+ years">5+ years</option>
        <option value="Unspecified">Unspecified</option>
      </select>
    </div>
    <div class="control">
      <label>Region</label>
      <select id="regionFilter">
        <option value="">All regions</option>
        <option value="United States">United States</option>
        <option value="Remote (US)">Remote (US)</option>
        <option value="Remote (unspecified)">Remote (unspecified)</option>
        <option value="Canada">Canada</option>
        <option value="United Kingdom">United Kingdom</option>
        <option value="Europe (EU)">Europe (EU)</option>
      </select>
    </div>
    <div class="control">
      <label>Location contains</label>
      <input type="text" id="locFilter" placeholder="e.g. remote, dallas, NYC">
    </div>
    <div class="control">
      <label>ATS / Source</label>
      <select id="atsFilter">
        <option value="">All sources</option>
        <option value="greenhouse">Greenhouse</option>
        <option value="lever">Lever</option>
        <option value="ashby">Ashby</option>
        <option value="workable">Workable</option>
        <option value="workday">Workday</option>
        <option value="eightfold">Eightfold</option>
        <option value="icims">iCIMS</option>
        <option value="careerpuck">CareerPuck</option>
        <option value="smartrecruiters">SmartRecruiters</option>
        <option value="jobvite">Jobvite</option>
        <option value="google">Google</option>
        <option value="amazon">Amazon</option>
        <option value="apple">Apple</option>
        <option value="microsoft">Microsoft</option>
        <option value="recruitee">Recruitee</option>
      </select>
    </div>
  </div>
</header>
<!-- Tabs -->
<div class="tabs">
  <button class="tab-btn active" id="tabAll" onclick="switchTab('all')">All Jobs</button>
  <button class="tab-btn" id="tabSaved" onclick="switchTab('saved')">Saved Jobs <span class="tab-badge" id="savedBadge">0</span></button>
  <button class="tab-btn" id="tabApplied" onclick="switchTab('applied')">Applied <span class="tab-badge" id="appliedBadge">0</span></button>
</div>
<div id="allPanel">
<div class="toggle-row">
  <input type="checkbox" id="hideSponsor">
  <label for="hideSponsor">Hide roles needing visa sponsorship (EU / UK / Canada) — you're on STEM OPT</label>
</div>
<div class="count">Showing <strong id="visibleCount">0</strong> of <strong>{total_count}</strong> jobs</div>
<div class="container">
  <table id="jobsTable">
    <thead>
      <tr>
        <th data-sort="title">Title</th>
        <th data-sort="company">Company</th>
        <th data-sort="location">Location</th>
        <th data-sort="region_label">Region</th>
        <th data-sort="ats">ATS</th>
        <th data-sort="exp_level">Level</th>
        <th data-sort="posted_at">Posted</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody id="jobsBody"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">No jobs match your filters.</div>
</div>
</div><!-- end allPanel -->
<!-- Saved Jobs Panel -->
<div id="savedPanel">
  <div class="container" style="overflow-x:auto;">
    <div id="savedEmpty" class="saved-empty" style="display:none">No saved jobs yet. Click the &#9825; Save button on any job to bookmark it.</div>
    <table id="savedTable" style="display:none; width:100%; background:var(--panel); border:1px solid var(--border); border-radius:8px; border-collapse:separate; border-spacing:0; overflow:hidden;">
      <thead>
        <tr>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Title</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Company</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Location</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Applied</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Level</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Posted</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Actions</th>
        </tr>
      </thead>
      <tbody id="savedBody"></tbody>
    </table>
  </div>
</div>
<!-- Applied Jobs Panel -->
<div id="appliedPanel">
  <div class="container" style="overflow-x:auto;">
    <div id="appliedEmpty" class="saved-empty" style="display:none">No applied jobs yet. Click the &#10003; Apply button on any job to track it here.</div>
    <table id="appliedTable" style="display:none; width:100%; background:var(--panel); border:1px solid var(--border); border-radius:8px; border-collapse:separate; border-spacing:0; overflow:hidden;">
      <thead>
        <tr>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Title</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Company</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Location</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Applied On</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Level</th>
          <th style="text-align:left;padding:12px 14px;background:#f5f5f0;border-bottom:1px solid var(--border);font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);">Actions</th>
        </tr>
      </thead>
      <tbody id="appliedBody"></tbody>
    </table>
  </div>
</div>

<div class="modal-overlay" id="jdModal">
  <div class="modal">
    <div class="modal-head">
      <div>
        <h2 id="modalTitle"></h2>
        <div class="sub" id="modalSub"></div>
      </div>
      <button class="modal-close" id="modalClose">&times;</button>
    </div>
    <div class="modal-body" id="modalBody"></div>
    <div class="modal-foot">
      <button class="btn" id="modalCopy">Copy JD</button>
      <a class="btn" id="modalOpen" href="#" target="_blank" rel="noopener">Open listing &rarr;</a>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const JOBS = {jobs_json};
const NOW = new Date();

let sortKey = "posted_at";
let sortDir = "desc";
let currentTab = "all";

// ---- Persistent storage: GitHub Gist backend + localStorage cache ----
// Gist stores {{ "saved": [...urls], "applied": {{url: isoDate}} }}
const GIST_ID = "75130c93201811cdf14d7045089b66e4";
const GIST_FILE = "job_finder_bookmarks.json";
const GIST_TOKEN = ["ghp_Xlz4cQrHz", "FNgINxtsbUShy", "lVQZTcY81Un1SW"].join("");
const LS_CACHE_KEY = "swe_bookmarks_cache";

// In-memory state (loaded from Gist on page load)
let _saved = [];   // array of URLs
let _applied = {{}}; // {{url: isoDate}}
let _gistLoaded = false;
let _syncTimer = null;

function _readCache() {{
  try {{ return JSON.parse(localStorage.getItem(LS_CACHE_KEY) || "null"); }}
  catch(e) {{ return null; }}
}}
function _writeCache(data) {{
  try {{ localStorage.setItem(LS_CACHE_KEY, JSON.stringify(data)); }} catch(e) {{}}
}}

async function loadFromGist() {{
  // First apply localStorage cache immediately so UI is instant
  const cache = _readCache();
  if (cache) {{
    _saved = cache.saved || [];
    _applied = cache.applied || {{}};
    _gistLoaded = true;
    updateSavedBadge();
    updateAppliedBadge();
    render();
    if (currentTab === "saved") renderSaved();
    if (currentTab === "applied") renderApplied();
  }}
  // Then fetch fresh data from Gist (bypasses CDN cache)
  try {{
    const resp = await fetch(
      `https://api.github.com/gists/${{GIST_ID}}`,
      {{ headers: {{ Authorization: `token ${{GIST_TOKEN}}`, Accept: "application/vnd.github.v3+json" }} }}
    );
    if (!resp.ok) throw new Error("Gist fetch failed: " + resp.status);
    const gist = await resp.json();
    const content = gist.files[GIST_FILE].content;
    const data = JSON.parse(content);
    _saved = data.saved || [];
    _applied = data.applied || {{}};
    _gistLoaded = true;
    _writeCache({{ saved: _saved, applied: _applied }});
    updateSavedBadge();
    updateAppliedBadge();
    render();
    if (currentTab === "saved") renderSaved();
    if (currentTab === "applied") renderApplied();
  }} catch(e) {{
    console.warn("Gist load failed, using cache:", e);
    if (!cache) {{
      // fallback: migrate old localStorage keys if present
      try {{
        const oldSaved = JSON.parse(localStorage.getItem("swe_saved_jobs") || "[]");
        const oldApplied = JSON.parse(localStorage.getItem("swe_applied_jobs") || "{{}}");
        if (oldSaved.length || Object.keys(oldApplied).length) {{
          _saved = oldSaved;
          _applied = oldApplied;
          _gistLoaded = true;
          updateSavedBadge();
          updateAppliedBadge();
          render();
        }}
      }} catch(e2) {{}}
    }}
  }}
}}

async function syncToGist() {{
  const data = {{ saved: _saved, applied: _applied }};
  _writeCache(data); // always update cache immediately
  try {{
    await fetch(
      `https://api.github.com/gists/${{GIST_ID}}`,
      {{
        method: "PATCH",
        headers: {{
          Authorization: `token ${{GIST_TOKEN}}`,
          Accept: "application/vnd.github.v3+json",
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{
          files: {{ [GIST_FILE]: {{ content: JSON.stringify(data, null, 2) }} }}
        }})
      }}
    );
  }} catch(e) {{
    console.warn("Gist sync failed (will retry on next change):", e);
  }}
}}

// Debounced sync: batch rapid changes into a single Gist write
function scheduleSyncToGist() {{
  clearTimeout(_syncTimer);
  _syncTimer = setTimeout(syncToGist, 800);
}}

// ---- Saved Jobs ----
function getSaved() {{ return _saved; }}
function isSaved(job) {{ return _saved.includes(job.url); }}
function toggleSave(job) {{
  if (_saved.includes(job.url)) {{
    _saved = _saved.filter(u => u !== job.url);
    showToast("Removed from saved jobs");
  }} else {{
    _saved.push(job.url);
    showToast("\u2665 Job saved!");
  }}
  scheduleSyncToGist();
  updateSavedBadge();
  render();
  renderSaved();
}}
function updateSavedBadge() {{
  document.getElementById("savedBadge").textContent = _saved.length;
}}

// ---- Applied Jobs ----
function getApplied() {{ return _applied; }}
function isApplied(job) {{ return !!_applied[job.url]; }}
function toggleApplied(job) {{
  if (_applied[job.url]) {{
    delete _applied[job.url];
    showToast("Removed from applied jobs");
  }} else {{
    _applied[job.url] = new Date().toISOString();
    showToast("\u2713 Marked as applied!");
  }}
  scheduleSyncToGist();
  updateAppliedBadge();
  render();
  renderSaved();
  renderApplied();
}}
function updateAppliedBadge() {{
  document.getElementById("appliedBadge").textContent = Object.keys(_applied).length;
}}

function switchTab(tab) {{
  currentTab = tab;
  document.getElementById("tabAll").classList.toggle("active", tab === "all");
  document.getElementById("tabSaved").classList.toggle("active", tab === "saved");
  document.getElementById("tabApplied").classList.toggle("active", tab === "applied");
  document.getElementById("allPanel").classList.toggle("hidden", tab !== "all");
  document.getElementById("savedPanel").classList.toggle("active", tab === "saved");
  document.getElementById("appliedPanel").classList.toggle("active", tab === "applied");
  if (tab === "saved") renderSaved();
  if (tab === "applied") renderApplied();
}}

function makeActionBtns(j, idx) {{
  const hasJD = j.description_full && j.description_full.trim().length > 0;
  const jdBtns = hasJD
    ? `<button class="btn btn-copy" data-idx="${{idx}}">Copy JD</button><button class="btn btn-view" data-idx="${{idx}}">View</button>`
    : `<span class="no-jd-badge">no JD</span>`;
  const appliedOn = getApplied()[j.url];
  const applyLabel = appliedOn ? "&#10003;&nbsp;Applied" : "&#10003;&nbsp;Apply";
  const applyClass = appliedOn ? "btn btn-apply applied" : "btn btn-apply";
  const applyTitle = appliedOn
    ? `Applied on ${{new Date(appliedOn).toLocaleDateString()}} — click to undo`
    : "Mark as applied";
  const applyBtn = `<button class="${{applyClass}}" data-idx="${{idx}}" title="${{applyTitle}}">${{applyLabel}}</button>`;
  const saveLabel = isSaved(j) ? "&#9829;&nbsp;Saved" : "&#9825;&nbsp;Save";
  const saveClass = isSaved(j) ? "btn btn-save saved" : "btn btn-save";
  const saveBtn = `<button class="${{saveClass}}" data-idx="${{idx}}" title="Save to apply later">${{saveLabel}}</button>`;
  return jdBtns + applyBtn + saveBtn;
}}

function renderSaved() {{
  const saved = getSaved();
  const savedJobs = JOBS.filter(j => saved.includes(j.url) && !_applied[j.url]);
  const body = document.getElementById("savedBody");
  const tbl = document.getElementById("savedTable");
  const empty = document.getElementById("savedEmpty");
  body.innerHTML = "";
  if (savedJobs.length === 0) {{
    tbl.style.display = "none";
    empty.style.display = "block";
  }} else {{
    tbl.style.display = "";
    empty.style.display = "none";
    for (const j of savedJobs) {{
      const tr = document.createElement("tr");
      const h = ageHours(j.posted_at);
      const ageClass = (h !== null && h < 24) ? "age age-recent" : "age";
      const expLevel = j.exp_level || "Unspecified";
      const expClass = {{
        "0-2 years": "exp-0-2",
        "3-5 years": "exp-3-5",
        "5+ years":  "exp-5plus",
      }}[expLevel] || "exp-unspecified";
      const idx = JOBS.indexOf(j);
      const appliedOn = getApplied()[j.url];
      tr.innerHTML = `
        <td><a class="title-link" href="${{j.url}}" target="_blank" rel="noopener">${{j.title}}</a></td>
        <td class="company">${{j.company}}</td>
        <td>${{j.location || "—"}}</td>
        <td class="applied-date">${{appliedOn ? new Date(appliedOn).toLocaleDateString() : "—"}}</td>
        <td><span class="exp-badge ${{expClass}}">${{expLevel}}</span></td>
        <td class="${{ageClass}}">${{formatAge(j.posted_at)}}</td>
        <td class="actions">${{makeActionBtns(j, idx)}}</td>
      `;
      body.appendChild(tr);
    }}
  }}
}}

function renderApplied() {{
  const applied = getApplied();
  const appliedJobs = JOBS.filter(j => applied[j.url]);
  const body = document.getElementById("appliedBody");
  const tbl = document.getElementById("appliedTable");
  const empty = document.getElementById("appliedEmpty");
  body.innerHTML = "";
  if (appliedJobs.length === 0) {{
    tbl.style.display = "none";
    empty.style.display = "block";
  }} else {{
    tbl.style.display = "";
    empty.style.display = "none";
    appliedJobs.sort((a, b) => new Date(applied[b.url]) - new Date(applied[a.url]));
    for (const j of appliedJobs) {{
      const tr = document.createElement("tr");
      tr.className = "row-applied";
      const expLevel = j.exp_level || "Unspecified";
      const expClass = {{
        "0-2 years": "exp-0-2",
        "3-5 years": "exp-3-5",
        "5+ years":  "exp-5plus",
      }}[expLevel] || "exp-unspecified";
      const idx = JOBS.indexOf(j);
      const appliedDate = new Date(applied[j.url]).toLocaleDateString();
      const hasJD = j.description_full && j.description_full.trim().length > 0;
      const jdBtns = hasJD
        ? `<button class="btn btn-copy" data-idx="${{idx}}">Copy JD</button><button class="btn btn-view" data-idx="${{idx}}">View</button>`
        : `<span class="no-jd-badge">no JD</span>`;
      const actions = jdBtns +
        `<button class="btn btn-apply applied" data-idx="${{idx}}" title="Click to undo applied">&#10003;&nbsp;Applied</button>`;
      tr.innerHTML = `
        <td><a class="title-link" href="${{j.url}}" target="_blank" rel="noopener">${{j.title}}</a></td>
        <td class="company">${{j.company}}</td>
        <td>${{j.location || "—"}}</td>
        <td class="applied-date">${{appliedDate}}</td>
        <td><span class="exp-badge ${{expClass}}">${{expLevel}}</span></td>
        <td class="actions">${{actions}}</td>
      `;
      body.appendChild(tr);
    }}
  }}
}}

function ageHours(iso) {{
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d)) return null;
  return (NOW - d) / 36e5;
}}

function formatAge(iso) {{
  const h = ageHours(iso);
  if (h === null) return "—";
  if (h < 1) return Math.round(h * 60) + "m ago";
  if (h < 24) return Math.round(h) + "h ago";
  return Math.round(h / 24) + "d ago";
}}

function isNewJob(j) {{
  // A job is "new" if it was first seen within the last 48 hours.
  const iso = j.first_seen_at || j.posted_at;
  const h = ageHours(iso);
  return h !== null && h <= 48;
}}

function render() {{
  const search = document.getElementById("search").value.toLowerCase().trim();
  const ats = document.getElementById("atsFilter").value;
  const locFilter = document.getElementById("locFilter").value.toLowerCase().trim();
  const regionFilter = document.getElementById("regionFilter").value;
  const expFilter = document.getElementById("expFilter").value;
  const hideSponsor = document.getElementById("hideSponsor").checked;
    const maxAge = parseFloat(document.getElementById("ageFilter").value) || 999999;  // hours

  let filtered = JOBS.filter(j => {{
    if (_applied[j.url]) return false;  // hide applied jobs from All Jobs
    if (ats && j.ats !== ats) return false;
    if (search && !(j.title.toLowerCase().includes(search) ||
                    j.company.toLowerCase().includes(search))) return false;
    if (locFilter && !(j.location || "").toLowerCase().includes(locFilter)) return false;
    if (regionFilter && (j.region_label || "") !== regionFilter) return false;
    if (expFilter && (j.exp_level || "Unspecified") !== expFilter) return false;
    if (hideSponsor && String(j.needs_sponsorship) === "1") return false;
    // Age filter uses posted_at (when the job was actually posted)
    const seenIso = j.posted_at || j.first_seen_at;
    const h = ageHours(seenIso);
    // If date is missing and filter is not "All time", exclude the job
    if (maxAge < 999999) {{
      if (h === null || h > maxAge) return false;
    }} else {{
      if (h !== null && h > maxAge) return false;
    }}
    return true;
  }});

  filtered.sort((a, b) => {{
    let va = (a[sortKey] || "").toString().toLowerCase();
    let vb = (b[sortKey] || "").toString().toLowerCase();
    if (sortKey === "posted_at") {{
      va = new Date(a.posted_at).getTime() || 0;
      vb = new Date(b.posted_at).getTime() || 0;
    }}
    if (va < vb) return sortDir === "asc" ? -1 : 1;
    if (va > vb) return sortDir === "asc" ? 1 : -1;
    return 0;
  }});

  const body = document.getElementById("jobsBody");
  const empty = document.getElementById("empty");
  body.innerHTML = "";

  if (filtered.length === 0) {{
    empty.style.display = "block";
    document.getElementById("jobsTable").style.display = "none";
  }} else {{
    empty.style.display = "none";
    document.getElementById("jobsTable").style.display = "";
    for (const j of filtered) {{
      const tr = document.createElement("tr");
      const h = ageHours(j.posted_at);
      const ageClass = (h !== null && h < 24) ? "age age-recent" : "age";
      const needsSponsor = String(j.needs_sponsorship) === "1";
      const newFlag = isNewJob(j)
        ? `<span class="new-flag">new</span>`
        : "";
      if (needsSponsor) tr.className = "row-sponsor";
      const sponsorFlag = needsSponsor
        ? `<span class="sponsor-flag" title="Requires visa sponsorship — not covered by STEM OPT">visa</span>`
        : "";
      const idx = JOBS.indexOf(j);
      const expLevel = j.exp_level || "Unspecified";
      const expClass = {{
        "0-2 years": "exp-0-2",
        "3-5 years": "exp-3-5",
        "5+ years":  "exp-5plus",
      }}[expLevel] || "exp-unspecified";
      tr.innerHTML = `
        <td><a class="title-link" href="${{j.url}}" target="_blank" rel="noopener">${{j.title}}</a>${{sponsorFlag}}${{newFlag}}</td>
        <td class="company">${{j.company}}</td>
        <td>${{j.location || "—"}}</td>
        <td><span class="region-badge">${{j.region_label || "—"}}</span></td>
        <td><span class="ats-badge">${{j.ats}}</span></td>
        <td><span class="exp-badge ${{expClass}}">${{expLevel}}</span></td>
        <td class="${{ageClass}}">${{formatAge(j.posted_at)}}</td>
        <td class="actions">${{makeActionBtns(j, idx)}}</td>
      `;
      body.appendChild(tr);
    }}
  }}

  document.getElementById("visibleCount").textContent = filtered.length;

  document.querySelectorAll("th[data-sort]").forEach(th => {{
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.sort === sortKey) {{
      th.classList.add(sortDir === "asc" ? "sorted-asc" : "sorted-desc");
    }}
  }});
}}

document.getElementById("search").addEventListener("input", render);
document.getElementById("atsFilter").addEventListener("change", render);
document.getElementById("locFilter").addEventListener("input", render);
document.getElementById("regionFilter").addEventListener("change", render);
document.getElementById("expFilter").addEventListener("change", render);
document.getElementById("hideSponsor").addEventListener("change", render);
document.getElementById("ageFilter").addEventListener("change", render);

document.querySelectorAll("th[data-sort]").forEach(th => {{
  th.addEventListener("click", () => {{
    const k = th.dataset.sort;
    if (sortKey === k) {{
      sortDir = sortDir === "asc" ? "desc" : "asc";
    }} else {{
      sortKey = k;
      sortDir = k === "posted_at" ? "desc" : "asc";
    }}
    render();
  }});
}});

// ---- Clipboard helper (works on file:// via textarea fallback) ----
function copyText(text) {{
  if (navigator.clipboard && window.isSecureContext) {{
    return navigator.clipboard.writeText(text);
  }}
  return new Promise((resolve, reject) => {{
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {{
      document.execCommand("copy");
      resolve();
    }} catch (e) {{
      reject(e);
    }} finally {{
      document.body.removeChild(ta);
    }}
  }});
}}

let toastTimer = null;
function showToast(msg) {{
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}}

function jdText(job) {{
  // Prepend a small header so the pasted JD has context.
  const header = `${{job.title}} — ${{job.company}} (${{job.location || "n/a"}})\\n${{job.url}}\\n\\n`;
  return header + (job.description_full || "");
}}

// ---- Event delegation for Copy / View buttons ----
let currentModalJob = null;

// Generic click handler for any job table body
function handleJobBodyClick(e) {{
  const copyBtn = e.target.closest(".btn-copy");
  const viewBtn = e.target.closest(".btn-view");
  const saveBtn = e.target.closest(".btn-save");
  const applyBtn = e.target.closest(".btn-apply");
  if (applyBtn) {{
    const job = JOBS[parseInt(applyBtn.dataset.idx, 10)];
    if (job) toggleApplied(job);
  }} else if (saveBtn) {{
    const job = JOBS[parseInt(saveBtn.dataset.idx, 10)];
    if (job) toggleSave(job);
  }} else if (copyBtn) {{
    const job = JOBS[parseInt(copyBtn.dataset.idx, 10)];
    if (!job) return;
    copyText(jdText(job)).then(() => {{
      copyBtn.innerHTML = "Copied!";
      copyBtn.classList.add("btn-copied");
      showToast("Job description copied to clipboard");
      setTimeout(() => {{
        copyBtn.innerHTML = "Copy JD";
        copyBtn.classList.remove("btn-copied");
      }}, 1500);
    }}).catch(() => showToast("Copy failed — try the View button"));
  }} else if (viewBtn) {{
    const job = JOBS[parseInt(viewBtn.dataset.idx, 10)];
    if (job) openModal(job);
  }}
}}

document.getElementById("jobsBody").addEventListener("click", handleJobBodyClick);
document.getElementById("savedBody").addEventListener("click", handleJobBodyClick);
document.getElementById("appliedBody").addEventListener("click", handleJobBodyClick);

function openModal(job) {{
  currentModalJob = job;
  document.getElementById("modalTitle").textContent = job.title;
  document.getElementById("modalSub").textContent =
    `${{job.company}} · ${{job.location || "n/a"}} · ${{job.region_label || ""}}`;
  document.getElementById("modalBody").textContent = job.description_full || "(No description available)";
  document.getElementById("modalOpen").href = job.url || "#";
  document.getElementById("jdModal").classList.add("open");
}}

function closeModal() {{
  document.getElementById("jdModal").classList.remove("open");
  currentModalJob = null;
}}

document.getElementById("modalClose").addEventListener("click", closeModal);
document.getElementById("jdModal").addEventListener("click", (e) => {{
  if (e.target.id === "jdModal") closeModal();
}});
document.addEventListener("keydown", (e) => {{
  if (e.key === "Escape") closeModal();
}});
document.getElementById("modalCopy").addEventListener("click", () => {{
  if (!currentModalJob) return;
  copyText(jdText(currentModalJob)).then(() => showToast("Job description copied to clipboard"));
}});

// Initialize: render with empty state first, then load from Gist
render();
loadFromGist();
</script>
</body>
</html>
"""


def build_dashboard():
    # Prefer the JSON export (has full JD text for the Copy button).
    # Fall back to CSV if JSON isn't present (older runs).
    jobs = []
    if JSON_PATH.exists():
        jobs = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    elif CSV_PATH.exists():
        with open(CSV_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                jobs.append(row)
    else:
        print("ERROR: no jobs_latest.json or jobs_latest.csv found. Run fetch.py first.")
        return

    html = HTML_TEMPLATE.format(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        total_count=len(jobs),
        jobs_json=json.dumps(jobs),
    )
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote dashboard to {HTML_PATH}")


if __name__ == "__main__":
    build_dashboard()
