# 🗺️ Maps Company Scraper

Scrape business listings from **Google Maps without any Google API key**.
Type a natural request like *"show me the IT companies in Mohali"* and get back:

| Company | Website | Phone | Email | Address | Category | Rating | Maps link |
|---|---|---|---|---|---|---|---|

Export everything to **CSV / Excel / JSON**.

## How it works (matches the architecture)

```
User Query
   │  "IT Companies in Mohali"
   ▼
Query Parsing             ← Rule-based regex parser extracts category + location
   ▼
Data Collection           ← Playwright drives a real Chromium browser over Google Maps
   ▼
Company Discovery         ← name, maps URL, website, phone, address
   ▼
Website Enrichment        ← visits each site's contact/about pages, extracts emails
   ▼
Data Validation           ← dedupe, normalize phones, validate emails/websites
   ▼
Structured Output         ← CSV / Excel / JSON  +  live web UI
```

## Tech stack
- **Backend:** FastAPI + Uvicorn
- **Browser automation:** Playwright (Chromium) — replaces the Google Places API, no key needed
- **AI:** Rule-based parser — parses the query into a structured category + location without needing any API keys
- **Enrichment:** httpx + BeautifulSoup
- **Frontend:** plain HTML / CSS / JS with live progress (Server-Sent Events)

## Setup

### macOS / Linux

```bash
# 1. Create a virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install the Chromium browser Playwright needs
playwright install chromium

# 5. Run the server
uvicorn app.main:app --reload --port 8011
```

### Windows (PowerShell)

```powershell
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install the Chromium browser Playwright needs
python -m playwright install chromium

# 5. Run the server
uvicorn app.main:app --reload --port 8011
```

### Running Without Activating the Virtual Environment
You can also start the server directly using the virtual environment's executable:
```bash
./.venv/bin/uvicorn app.main:app --reload --port 8011
```

Open **http://127.0.0.1:8011** in your browser.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `MAX_RESULTS` | `20` | Companies to scrape per query (per-request override capped at 120) |
| `HEADLESS` | `true` | `false` to watch the browser work |
| `ENRICH_WEBSITES` | `true` | Visit sites to find emails |
| `SCRAPE_TIMEOUT_MS` | `45000` | Per-page navigation timeout |

## API

- `POST /api/search` — `{ "query": "...", "max_results"?: 20, "enrich"?: true }` → JSON results
- `GET  /api/stream?query=...&max_results=...&enrich=...` — Server-Sent Events with live progress + results
- `POST /api/export/{csv|xlsx|json}` — body = results array → downloadable file
- `GET  /api/health` — sanity check (`{status}`)

## Notes & limits
- Scraping Google Maps is against Google's ToS; use responsibly, for low volumes,
  and respect target websites. This tool is for educational / authorized use.
- Google occasionally changes Maps' HTML; if extraction breaks, the selectors in
  `app/scraper.py` are the place to adjust.
- Emails only appear when a company publishes one on its website — many won't.



map scrap/
├── .env                  ← local configuration (optional)
├── requirements.txt
├── README.md             ← full setup + API docs
├── app/
│   ├── main.py           ← FastAPI: /api/search, /api/stream (live), /api/export
│   ├── ai_agent.py       ← rule-based query parser (category + location)
│   ├── scraper.py        ← Playwright Google Maps scraper
│   ├── enrichment.py     ← email extraction from websites
│   ├── validation.py     ← dedupe, phone/email validation
│   └── export.py         ← CSV / Excel / JSON
└── frontend/             ← HTML + CSS + JS UI with live progress