# TITO Cyber Tender Intelligence Portal — Live Edition

This package wires your dashboard up to a **real daily scraper** running for free
on GitHub's servers. No PC needs to stay on. No server to pay for.

```
your-repo/
├── .github/workflows/daily-scrape.yml   ← runs the scraper every day, automatically
├── scraper/
│   ├── scrape.py                        ← the scraper (eTenders, Gov Gazette, SADC)
│   └── requirements.txt
├── data/
│   └── tenders.json                     ← scraper's output — the dashboard reads this
└── docs/
    └── index.html                       ← the dashboard (publish this via GitHub Pages)
```

## How it works, end to end

1. **Every day at 06:00 SAST**, GitHub spins up a free temporary Linux machine,
   runs `scraper/scrape.py`, and that script:
   - Searches eTenders.gov.za, the SA Government Gazette, and 9 SADC procurement
     portals for cybersecurity/AI/ICT keywords
   - Filters results down to **only tenders that close in 2026 and haven't closed yet**
   - Writes everything to `data/tenders.json`
2. GitHub Actions **commits that file back to your repo** automatically.
3. Your dashboard (`docs/index.html`), published as a website via **GitHub Pages**,
   fetches `data/tenders.json` every time it's opened, and again whenever you click
   **⟳ Sync Now**.
4. A badge in the sidebar tells you honestly whether you're looking at:
   - 🟢 **LIVE DATA** — real tenders the scraper just found
   - 🟡 **SEED DATA** — the scraper ran, but every government portal blocked it or
     changed its page layout, so curated fallback tenders are shown instead
   - ⚪ **OFFLINE SAMPLE** — the dashboard couldn't even reach `data/tenders.json`
     (usually because it's been opened as a local file instead of a published site)

## Deploy it — 10 minutes, no coding required

### 1. Create the GitHub repository
- Go to [github.com/new](https://github.com/new)
- Name it anything, e.g. `tito-tender-portal`
- Set it to **Public** (required for free GitHub Pages) or use GitHub Pro/Team for private
- Click **Create repository**

### 2. Upload these files
- On the new repo's page, click **Add file → Upload files**
- Drag in this entire folder structure (keep the folder names exactly as they are:
  `.github/workflows/daily-scrape.yml`, `scraper/`, `data/`, `docs/`)
- Commit directly to the `main` branch

### 3. Turn on GitHub Pages
- Go to **Settings → Pages** (left sidebar)
- Under "Build and deployment" → Source: **Deploy from a branch**
- Branch: `main`, folder: **`/docs`**
- Click **Save**
- GitHub gives you a URL like `https://yourusername.github.io/tito-tender-portal/`
  — that's your live dashboard, bookmark it

### 4. Let the scraper run
- Go to the **Actions** tab → you'll see "Daily Cyber Tender Scrape"
- Click it, then click **Run workflow** (top right) to trigger the first run manually
- Wait ~1 minute, refresh — you'll see a green checkmark when it's done
- After this, it runs **automatically every day** at 06:00 SAST — you never have to touch it again

### 5. Open your dashboard
- Visit the GitHub Pages URL from step 3
- The sidebar will show 🟢 LIVE DATA (or 🟡 SEED DATA if government portals are
  currently blocking automated requests — see note below)

## Important: government sites actively block scrapers

This is the honest part. eTenders.gov.za and most SADC procurement portals run
anti-bot protection (Cloudflare, IP blocking, JavaScript challenges). The scraper
**will** sometimes get blocked — that's not a bug in this code, it's how those
sites are built. When that happens:

- The scraper doesn't crash or leave you with an empty dashboard
- It automatically falls back to a small curated seed list of real, representative
  tender types (clearly labeled 🟡 SEED DATA so you're never misled)
- You can manually update `scraper/scrape.py`'s `seed_tenders()` function with
  real tenders you find by checking the portals yourself, as a stopgap

**To get past blocking long-term**, the realistic options are:
- A paid scraping API (e.g. ScraperAPI, Bright Data) that handles anti-bot
  measures — costs money but works reliably
- Registering for any official tender notification/RSS feed eTenders offers
  (check their site for an API or subscription option)
- Manually checking the portals weekly and updating the seed list

I built the architecture to be honest about this rather than pretending it's
solved — the scraper genuinely tries the live sites first, every single day.

## Updating the scraper later

Edit `scraper/scrape.py` — particularly the CSS selectors inside `scrape_etenders()`,
`scrape_government_gazette()`, and `scrape_sadc_portals()` — if a portal changes its
page structure and stops returning results. Commit the change, and tomorrow's
scheduled run will use it automatically.

## Manual local test (optional)

```bash
cd scraper
pip install -r requirements.txt
python3 scrape.py
cat ../data/tenders.json
```
