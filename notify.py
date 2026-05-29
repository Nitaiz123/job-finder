"""
Send a job-fetch summary email via SendGrid after each workflow run.

Usage:
    python notify.py <new_count> <total_count> <run_url>

Environment variables required:
    SENDGRID_API_KEY  — SendGrid API key with Mail Send permission
    NOTIFY_TO         — recipient email address
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
FROM_EMAIL   = "nitaipujari@gmail.com"
FROM_NAME    = "Job Finder Bot"

JSON_PATH = Path(__file__).parent / "jobs_latest.json"


def load_new_jobs(new_count: int):
    """Return the first `new_count` jobs from jobs_latest.json (newest first)."""
    if not JSON_PATH.exists() or new_count == 0:
        return []
    try:
        jobs = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        # jobs are sorted newest-first; the first new_count are the freshest
        return jobs[:new_count]
    except Exception:
        return []


def build_html(new_count: int, total_count: int, run_url: str, jobs: list) -> str:
    now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    dashboard_url = "https://nitaiz123.github.io/job-finder/"

    rows = ""
    for j in jobs[:20]:   # cap at 20 in the email
        title    = j.get("title", "—")
        company  = j.get("company", "—")
        location = j.get("location", "—")
        exp      = j.get("exp_level", "Unspecified")
        url      = j.get("url", "#")
        rows += f"""
        <tr>
          <td><a href="{url}" style="color:#1a73e8;text-decoration:none;">{title}</a></td>
          <td>{company}</td>
          <td>{location}</td>
          <td>{exp}</td>
        </tr>"""

    more = ""
    if new_count > 20:
        more = f'<p style="color:#555;font-size:13px;">…and {new_count - 20} more. <a href="{dashboard_url}">View all on the dashboard →</a></p>'

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#222;">
  <h2 style="color:#1a73e8;margin-bottom:4px;">🔔 Job Finder — Fresh Pull Complete</h2>
  <p style="color:#555;font-size:13px;margin-top:0;">{now}</p>

  <table style="border-collapse:collapse;width:100%;margin:12px 0;">
    <tr>
      <td style="padding:10px 16px;background:#e8f0fe;border-radius:6px;text-align:center;">
        <div style="font-size:28px;font-weight:700;color:#1a73e8;">{new_count}</div>
        <div style="font-size:12px;color:#555;">New jobs this run</div>
      </td>
      <td style="width:16px;"></td>
      <td style="padding:10px 16px;background:#f1f3f4;border-radius:6px;text-align:center;">
        <div style="font-size:28px;font-weight:700;color:#444;">{total_count}</div>
        <div style="font-size:12px;color:#555;">Total accumulated</div>
      </td>
    </tr>
  </table>

  <p>
    <a href="{dashboard_url}" style="display:inline-block;padding:10px 20px;background:#1a73e8;color:#fff;border-radius:5px;text-decoration:none;font-weight:600;">
      Open Dashboard →
    </a>
    &nbsp;
    <a href="{run_url}" style="display:inline-block;padding:10px 20px;background:#f1f3f4;color:#444;border-radius:5px;text-decoration:none;font-weight:600;">
      View Run Logs
    </a>
  </p>

  {"<h3 style='margin-bottom:8px;'>New jobs this run</h3>" if jobs else ""}
  {"<table style='border-collapse:collapse;width:100%;font-size:13px;'><thead><tr style='background:#f1f3f4;'><th style='padding:8px;text-align:left;'>Title</th><th style='padding:8px;text-align:left;'>Company</th><th style='padding:8px;text-align:left;'>Location</th><th style='padding:8px;text-align:left;'>Exp</th></tr></thead><tbody>" + rows + "</tbody></table>" if jobs else ""}
  {more}

  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="font-size:11px;color:#aaa;">
    You're receiving this because you set up job-finder notifications.<br>
    Runs automatically every 2 hours, 7am–9pm CDT.
  </p>
</body>
</html>
"""


def build_text(new_count: int, total_count: int, run_url: str, jobs: list) -> str:
    now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    lines = [
        f"Job Finder — Fresh Pull Complete ({now})",
        f"New jobs this run: {new_count}",
        f"Total accumulated: {total_count}",
        f"Dashboard: https://nitaiz123.github.io/job-finder/",
        f"Run logs: {run_url}",
        "",
    ]
    if jobs:
        lines.append("New jobs:")
        for j in jobs[:20]:
            lines.append(f"  - {j.get('title','?')} @ {j.get('company','?')} | {j.get('location','?')} | {j.get('exp_level','?')}")
            lines.append(f"    {j.get('url','')}")
    return "\n".join(lines)


def send_email(new_count: int, total_count: int, run_url: str):
    api_key  = os.environ.get("SENDGRID_API_KEY", "")
    to_email = os.environ.get("NOTIFY_TO", FROM_EMAIL)

    if not api_key:
        print("SENDGRID_API_KEY not set — skipping email notification.")
        return

    jobs = load_new_jobs(new_count)

    subject = (
        f"[Job Finder] {new_count} new job{'s' if new_count != 1 else ''} found"
        if new_count > 0
        else "[Job Finder] Fetch complete — no new jobs this run"
    )

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": build_text(new_count, total_count, run_url, jobs)},
            {"type": "text/html",  "value": build_html(new_count, total_count, run_url, jobs)},
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        SENDGRID_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Email sent to {to_email} (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"SendGrid error {e.code}: {body}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python notify.py <new_count> <total_count> <run_url>")
        sys.exit(1)
    send_email(
        new_count   = int(sys.argv[1]),
        total_count = int(sys.argv[2]),
        run_url     = sys.argv[3],
    )
