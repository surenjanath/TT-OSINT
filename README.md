# TT OSINT — Crime & Incident Intelligence Map (Trinidad & Tobago)

An **AI-powered geospatial intelligence platform** that ingests news from Trinidad & Tobago sources, extracts incident data using natural language processing (Ollama/LLM), geocodes locations, and visualizes events on an interactive national map. It functions as a **Caribbean OSINT (Open Source Intelligence) monitoring system** for crime, traffic accidents, fires, police activity, and public safety events.

---

## Features

- **Automated news ingestion** — RSS, web scraping, and JSON API support for sources (e.g. CNC3, Newsday, Trinidad Express, Loop TT)
- **AI incident extraction** — LLM-based extraction of incident type, location, date, severity, victims, weapons, and related entities (Ollama, configurable model)
- **Geocoding** — Nominatim (OpenStreetMap) with a built-in Trinidad & Tobago location fallback dictionary for streets, neighborhoods, and regions
- **Interactive map** — National map with incident markers, filters by category/region/date, and GeoJSON API
- **Incident list & detail** — Table view with filters; detail pages with source articles and extracted fields
- **Story clustering** — Articles covering the same event grouped into stories with optional link to a primary incident
- **Analytics & timeline** — Incident statistics, trends, and timeline views
- **Admin & operations** — Source management (add/edit/toggle/test), pipeline triggers (scrape → extract → full), moderation (approve/reject/edit/delete incidents, regeocode)
- **Export** — CSV export of incidents for external analysis

---

## Technology Stack

| Layer        | Technology |
|-------------|------------|
| Backend     | Python 3, Django 4.2 |
| Database    | SQLite (default; configurable for PostgreSQL) |
| AI / NLP    | [Ollama](https://ollama.ai/) (local LLM, e.g. `llama3`) |
| Geocoding   | Nominatim (OpenStreetMap) + TT location fallback dictionary |
| News ingest | `feedparser`, `requests`, `beautifulsoup4`, `lxml` |

---

## Project Structure

```
TT_OSINT/
├── tt_osint/           # Django project settings & root URLs
├── core/                # Shared templates, static assets, SystemSetting model
├── data/                # Optional: put db.sqlite3 here to deploy with the app (committed to git)
├── articles/            # News sources, Article/Story/ScrapeJob models, scraping & clustering
│   └── management/commands/
│       ├── scrape_news.py      # Scrape all or one source
│       ├── historical_scrape.py
│       ├── seed_sources.py     # Seed T&T news sources
│       ├── cluster_stories.py
│       └── clear_data.py
├── incidents/           # Incident/Person models, AI extraction, geocoding, API & views
│   └── management/commands/
│       └── process_articles.py # Run AI extraction on unprocessed articles
├── mockup/              # HTML mockups (admin panel, map, incident list, etc.)
├── manage.py
├── requirements.txt
├── PRD.md               # Product requirements document
└── README.md
```

---

## Prerequisites

- **Python 3.10+** (recommended)
- **Ollama** — Install from [ollama.ai](https://ollama.ai/) and pull a model, e.g.:
  ```bash
  ollama pull llama3
  ```
  The app uses this for incident extraction; without it, extraction will fail.

---

## Installation

1. **Clone or open the project**
   ```bash
   cd TT_OSINT
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # Linux/macOS
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment (optional)**  
   Defaults work with SQLite and local Ollama. Override if needed:
   - `OLLAMA_HOST` — e.g. `http://localhost:11434`
   - `OLLAMA_MODEL` — e.g. `llama3`
   - `SECRET_KEY` — set in production
   - For PostgreSQL: set `DATABASES` in `tt_osint/settings.py` (and install `psycopg2`).

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Seed news sources (optional but recommended)**
   ```bash
   python manage.py seed_sources
   ```

7. **Create a superuser (optional, for Django admin)**
   ```bash
   python manage.py createsuperuser
   ```

8. **Run the development server**
   ```bash
   python manage.py runserver
   ```
   Open **http://127.0.0.1:8000/**.

---

## Management Commands

| Command | Description |
|--------|-------------|
| `python manage.py scrape_news` | Scrape all active sources. Use `--source "Source Name"` to scrape one source. |
| `python manage.py process_articles` | Run AI extraction + geocoding on unprocessed articles. Use `--limit N` to cap how many to process. |
| `python manage.py seed_sources` | Load initial Trinidad & Tobago news sources (RSS/API). |
| `python manage.py historical_scrape` | Backfill articles by date range (see command help for args). |
| `python manage.py cluster_stories` | Group articles into stories (clustering). |
| `python manage.py clear_data` | Clear articles/incidents (see command help for options). |

**Typical pipeline:**  
`scrape_news` → `process_articles` (or use the Operations page / API to trigger the same flow).

---

## Main URLs & Pages

| Path | Description |
|------|-------------|
| `/` | Home — map and recent incidents |
| `/incidents/` | Incident list with filters |
| `/incidents/<id>/` | Incident detail (map, articles, extracted fields) |
| `/analytics/` | Analytics dashboard |
| `/timeline/` | Article/incident timeline |
| `/stories/` | Story list (clustered articles) |
| `/stories/<id>/` | Story detail |
| `/admin-panel/` | Moderation (approve/reject/edit incidents) |
| `/operations/` | Pipeline controls & source management |
| `/settings/` | System settings (e.g. AI extractor limit) |
| `/articles/` | Article list |
| `/articles/<id>/` | Article detail |
| `/django-admin/` | Django admin (if superuser created) |

---

## API Endpoints (summary)

- **Map & data:** `GET /api/incidents/geojson/`, `GET /api/incidents/stats/`, `GET /api/incidents/export/` (CSV)
- **Pipeline:** `POST /api/pipeline/scrape/`, `POST /api/pipeline/extract/`, `POST /api/pipeline/full/`, `GET /api/pipeline/status/`
- **Sources:** `GET /api/sources/`, add/edit/toggle/delete, test, fetch-sample
- **Moderation:** moderate, batch-moderate, delete incident, regeocode (single or all)
- **Settings:** e.g. `POST /api/settings/test-ai/` to test Ollama connection

(Exact request/response shapes are in `incidents/api.py` and `incidents/urls.py`.)

---

## Data Pipeline (high level)

```
News sources (RSS / Web / API)
    → Article scraper (articles app)
    → Article DB
    → AI extraction (Ollama) + geocoding (Nominatim + TT dict)
    → Incident DB (+ optional Person entities)
    → Map & list views, analytics, export
```

Incidents can be **pending**, **approved**, or **rejected**; the map and exports typically respect status. Low-confidence extractions can be reviewed in the admin panel.

---

## Configuration Notes

- **AI extractor limit:** Configurable via **Settings** in the UI (stored in `core.SystemSetting`, key `ai_extractor_limit`). `process_articles` uses this unless overridden by `--limit`.
- **Geocoding:** Uses Nominatim with a custom `User-Agent` (see `settings.NOMINATIM_USER_AGENT`). Rate-limiting and usage policies of the geocoding service apply.
- **Time zone:** `America/Port_of_Spain` in Django settings.
- **SQLite in repo (demo):** To use your own database on deploy, put it in **`data/db.sqlite3`** and commit it. The app will use `data/db.sqlite3` when present (e.g. on Heroku/App Platform). Locally, the root `db.sqlite3` is ignored by git; use `data/db.sqlite3` for the copy you push.

---

## Production deployment

The app is production-ready when run with the correct environment variables and a production WSGI server.

### 1. Environment variables

Copy `.env.example` to `.env` (or set variables in your platform). **Required in production:**

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Long random secret (e.g. `openssl rand -base64 48`). **Required** when `DEBUG=false`. |
| `ALLOWED_HOSTS` | Comma-separated hostnames, e.g. `yourdomain.com,www.yourdomain.com`. **Required** in production. |
| `DJANGO_DEBUG` | Set to `false` (or `0`) in production. |

**Optional — database:** Use PostgreSQL in production. Either set `DATABASE_URL` (e.g. `postgres://user:pass@host:5432/dbname`) or the `POSTGRES_*` variables (see `.env.example`). If neither is set, SQLite is used (suitable only for dev).

**Optional — AI / geocoding:** `OLLAMA_HOST`, `OLLAMA_MODEL` (defaults: `http://localhost:11434`, `llama3`). Restrict Ollama to trusted networks.

### 2. Install dependencies and collect static files

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Create a superuser if you need Django admin: `python manage.py createsuperuser`.

### 3. Run with Gunicorn

```bash
gunicorn tt_osint.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

For production, put Gunicorn behind a reverse proxy (e.g. Nginx, Caddy) that terminates SSL and sets `X-Forwarded-Proto` / `X-Forwarded-For` if needed.

### 4. Security (automatic when `DEBUG=false`)

When `DJANGO_DEBUG` is not `true`, the app enforces:

- `DJANGO_SECRET_KEY` must be set and not the default dev key.
- `ALLOWED_HOSTS` must be set (no `*`).
- Secure cookies, HSTS, XSS/clickjacking headers, and optional HTTPS redirect (`DJANGO_HTTPS_ONLY=true`, default).

Static files are served via **WhiteNoise** (no separate static server needed for moderate traffic).

### 5. Deploy on DigitalOcean (App Platform)

The repo includes a [DigitalOcean App Platform](https://docs.digitalocean.com/products/app-platform/) spec that uses **PostgreSQL** so data persists across deploys.

**Steps:**

1. **Push this repo to GitHub** (create a new repo and push if you haven’t already).

2. **Create an App** in [DigitalOcean](https://cloud.digitalocean.com/apps):
   - **Create App** → **GitHub** → select your `TT_OSINT` repo and branch (e.g. `main`).
   - Use the included spec: choose **Use existing app spec** and select `.do/app.yaml` (edit `github.repo` in that file to match your `owner/repo`). The spec adds a PostgreSQL 16 database and sets `DATABASE_URL` for the app.
   - Or create manually: add a **Database** (PostgreSQL 16), set **Build Command** `python manage.py collectstatic --noinput`, **Run Command** `python manage.py migrate --noinput && gunicorn tt_osint.wsgi:application --bind 0.0.0.0:$PORT --worker-tmp-dir /dev/shm --workers 2`, **HTTP Port** `8080`, and bind the database so the app gets `DATABASE_URL`.

3. **Set environment variables** (Settings → Environment Variables):
   - **Required:** `DJANGO_SECRET_KEY` (long random string), `ALLOWED_HOSTS` (your app hostname, e.g. `your-app-xxxxx.ondigitalocean.app` — no `https://`).
   - **Required:** `DJANGO_DEBUG` = `false`.
   - **Optional:** `OLLAMA_HOST`, `OLLAMA_MODEL` if you run Ollama elsewhere (App Platform doesn’t run Ollama).

4. **Deploy.** Open your app URL after the first deploy. Use **Console** to run `python manage.py createsuperuser` if you need Django admin.

**If you already have an app (no DB):** In the DO dashboard, add a **Database** (PostgreSQL) to the app, then in the web service’s environment variables add `DATABASE_URL` and set it to the database’s connection string (or use the “Bind to database” option so DO injects it). Redeploy so the app uses Postgres instead of SQLite.

**“Permission denied for schema public”:** On PostgreSQL 15+, the app user may not be allowed to create tables in `public`. You must run the GRANTs in **`scripts/create_app_schema.sql as admin, then set PG_SCHEMA=app; or try scripts/grant_public_schema.sql`** as the **admin** user, not as `db`. In DigitalOcean: open your **database** (the PostgreSQL resource) → **Connection details** → use the **doadmin** user and its password (not the `db` app user). Connect with psql or any client as `doadmin`, then run the two `GRANT` statements from the script (run one at a time to avoid paste issues). Then run `python manage.py migrate` again from the app console.

**Using doctl:** Edit `.do/app.yaml` and set `github.repo` to your repo (e.g. `your-username/TT_OSINT`). Then: `doctl apps create --spec .do/app.yaml`. Add `DJANGO_SECRET_KEY` and `ALLOWED_HOSTS` in the Control Panel.

---

## License & Author

Product concept and PRD: **Surenjanath Singh**.  
For full product vision and feature set, see **PRD.md**.
