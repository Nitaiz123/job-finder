# Deployment guide — GitHub Actions + Pages

This deploys the job finder as a scheduled GitHub Action that publishes a
public dashboard to GitHub Pages. **Total cost: $0.** Schedule: every 2 hours,
7am–9pm CT, every day (8 runs/day).

## What gets deployed

- **Main branch:** just the code. Clean history — no bot commits land here.
- **`data` branch (orphan):** persistent state (`companies.json`, `jobs.db`).
  Force-pushed each run as a single commit; no history accumulation.
- **GitHub Pages:** serves `dashboard.html` as `index.html`. Public URL.

## One-time setup (10 minutes)

### 1. Push the project to a new GitHub repo

```bash
cd job_finder
git init
git add -A
git commit -m "Initial commit"
git branch -M main
# Create a new repo on github.com first (e.g. "daily-jobs"), then:
git remote add origin git@github.com:YOURNAME/daily-jobs.git
git push -u origin main
```

### 2. Enable GitHub Pages with "GitHub Actions" source

In the repo on github.com:
1. Go to **Settings → Pages**.
2. Under **Source**, choose **GitHub Actions** (NOT "Deploy from a branch").
3. That's it — no other config needed.

### 3. Verify workflow permissions

Go to **Settings → Actions → General**, scroll to **Workflow permissions**:
- Select **Read and write permissions**.
- Check **Allow GitHub Actions to create and approve pull requests**.
- Save.

(The workflow's `permissions:` block already requests these, but the repo
setting must allow it.)

### 4. Trigger the first run

Two options:
- **Push any small change** to `main` (e.g. edit this file). The workflow
  runs on every push.
- **Or go to the Actions tab → "Fetch jobs & deploy dashboard" → Run workflow**.

The first run will:
- Take 4–8 minutes (bootstrap + fetch ~830 companies + discovery).
- Create the `data` branch automatically.
- Deploy the dashboard.

### 5. Find your dashboard URL

After the first successful run, the URL is shown in:
- The Actions tab → click the run → "deploy" job → look for the `page_url`.
- Or **Settings → Pages** shows it at the top.

Format: `https://YOURNAME.github.io/daily-jobs/`

## Day-to-day

- **The dashboard auto-refreshes** every 2 hours during the run window.
- **GitHub's cron is not punctual** — runs may be 5–30 minutes late, occasionally
  skipped under platform load. That's their service, not a bug here.
- **Check the Actions tab** if the dashboard hasn't updated in >4 hours.
- **Manual run anytime:** Actions tab → workflow → "Run workflow" button.

## Costs

- Public repo, GitHub free tier: **unlimited Actions minutes**.
- Pages: free, no bandwidth limits for non-commercial use.
- Estimated usage: ~8 runs/day × 5 min = 40 min/day = ~1,200 min/month.
  (Would still fit under the 2,000-min free tier even if the repo were private.)

## Going private later

If you decide to make the repo private:
- Actions minutes count against the 2,000/month free tier. 1,200/month is OK.
- GitHub Pages on private repos requires a paid plan (Pro $4/mo).
- The `data` branch and code branch can stay separate the same way.

## Stopping / pausing

- **Pause runs temporarily:** Actions tab → workflow → "..." → Disable workflow.
- **Stop entirely:** delete the workflow file or archive the repo.

## What's in the `data` branch?

Each run force-pushes a single commit containing:
- `companies.json` — current company list (with discovered + curated, plus
  health metadata)
- `jobs.db` — SQLite cache for repost detection (auto-pruned to last 60 days)
- `discovery_candidates.json` — pending candidates being validated

If you ever want to inspect or reset state, this branch is where it lives.
To reset everything: delete the `data` branch on GitHub and re-run.

## Known limitations on the cloud run

These are the same caveats from the main README, just relevant in cloud context:

- **Workday protected tenants** (Goldman Sachs, Shell, etc.) return 401/403 from
  GitHub's IP ranges. Run continues, those tenants show zero jobs.
- **iCIMS JS-gated portals** return zero jobs. By design.
- **ATS rate limits** — at 8 runs/day across ~830 companies, you're polite
  enough that no provider should rate-limit. If you ever raise the cadence
  and start seeing 429s in logs, dial back.
