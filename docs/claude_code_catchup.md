# Claude Code Catchup — 2026-06-27

A handoff document for continuing work in a new Claude Code session.

---

## Project: StarWolf

**Live URL:** starwolf.wolvertons.net  
**Repo:** github.com/traviswolverton/starwolf  
**Working directory:** `/opt/stargazing-app`  
**Git user:** travis  
**Stack:** Django 5.x + HTMX 2.x + Alpine.js 3.x, PostgreSQL 16, Redis 7, Docker Compose  
**Running containers:** `django` (port 8080), `db`, `redis`  

---

## Current Repo Structure

```
stargazing-app/
├── django/
│   ├── config/                  # Settings, URLs
│   ├── accounts/                # User model, RBAC, allauth, management commands
│   │   └── management/commands/
│   │       ├── create_local_admin.py
│   │       ├── offboard_user.py
│   │       ├── compute_heatmap.py      # run via cron 17:00 UTC daily
│   │       ├── populate_site_locations.py
│   │       └── enrich_notes.py
│   ├── engine/                  # Core domain logic (Python package)
│   │   ├── forecast.py          # Open-Meteo + 7timer API client
│   │   ├── scorer.py            # Composite night quality scorer
│   │   ├── bortle_lookup.py     # World Atlas GeoTIFF lookup
│   │   ├── ai_summary.py        # Ollama AI narrative summaries
│   │   ├── cache.py             # Redis wrapper
│   │   └── ai_config.py         # Ollama constants
│   ├── pages/                   # All Django views (views.py is large ~1200 lines)
│   ├── templates/               # Django templates
│   ├── static/css/main.css      # Single dark-theme stylesheet
│   └── Dockerfile.django
├── docs/
│   ├── API_GUIDE.md
│   ├── COMMANDS.md
│   └── claude_code_catchup.md   # this file
├── assets/
│   └── starwolf-logo.svg        # Not yet wired into any template
├── prompts/                     # Historical prompt/planning docs
├── data/                        # World_Atlas_2015.tif (gitignored, mounted read-only)
├── archive/                     # Legacy Streamlit files (gitignored, on-disk only)
├── requirements.txt             # Shared deps: requests, astral, rasterio, redis, psycopg2-binary, timezonefinder
├── docker-compose.yml           # django + db + redis only
├── release_notes.json           # User-facing changelog
├── CLAUDE.md                    # Behavioral guidelines (read this first)
└── README.md
```

---

## Auth & Users

- **Auth:** django-allauth — Google OAuth, GitHub OAuth, email/password
- **2FA:** TOTP via `allauth.mfa` — only fires for password-based (local admin) logins
- **Roles:** `guest`, `user`, `admin` — stored on `User.role`
- **`is_admin()`** method on user model checks `role == ADMIN`
- **No Cloudflare Access** — was removed; allauth is the sole auth layer
- **Create admin:** `docker compose exec django python manage.py create_local_admin email@example.com password`

---

## What Was Done This Session

### Nav & UI Modernization
- Nav slimmed to 50px, two-tier hierarchy (primary: Planner/Sites/Tonight's Sky Map; secondary/dimmed: Bortle Scorer, About, Developers)
- Active page gets a 2px teal underline via `request.resolver_match.url_name`
- User button replaced with teal-bordered initials avatar
- "Feedback" moved from nav to persistent footer link
- "API" replaced with "Developers" dropdown containing API Guide
- "Bortle" renamed to "Bortle Scorer", "Tonight's Forecast Map" renamed to "Tonight's Sky Map"
- Homepage step cards and setup cards: softer borders, box-shadow, 12px radius, teal left-border hierarchy

### Features Added Earlier (same session)
- Top 10 Sites Tonight table + star markers on heatmap
- "Data last gathered" stat bar on heatmap
- Heatmap auto-refresh cron (noon CDT daily via `compute_heatmap`)
- Planner: Location + Sites cards merged, live site count on slider drag (HTMX)
- Preferences redesigned as compact table (pill toggle, spinners, tooltips)
- Scoring weights moved to collapsed section on Planner page
- Display Name preference (saves to `user.first_name`, shown in nav, pre-fills feedback form)
- Full TOTP 2FA flow (all templates custom-styled)
- Feedback page gated behind login

### Repo Cleanup
- **Streamlit fully decommissioned** — all Streamlit files moved to `archive/` (gitignored)
- `docker-compose.yml` stripped to django + db + redis only
- Docs moved to `docs/` folder (`API_GUIDE.md`, `COMMANDS.md`)
- `qa/`, `.gitea/`, empty `nginx/` removed
- `starwolf-logo.svg` moved to `assets/`
- **`django/engine/` package created** — `forecast.py`, `scorer.py`, `bortle_lookup.py`, `ai_summary.py`, `cache.py`, `ai_config.py` moved from root into Django project
  - `scorer.py` now uses `django.db.connection` instead of SQLAlchemy
  - `ai_summary.py` now uses `django.db.connection` for app settings
  - `Dockerfile.django` no longer needs `COPY *.py` or `PYTHONPATH=/app`
- `requirements.txt` trimmed from 15 packages to 6 (removed streamlit, pandas, plotly, sqlalchemy, fastapi, uvicorn, slowapi, etc.)

---

## Key Technical Notes

### Database Access Pattern
Django views use `django.db.connection` directly (raw SQL) rather than ORM models for most queries — the schema predates the Django migration and uses raw tables (`sites`, `scoring_weights`, `app_settings`, `site_daily_scores`, etc.).

### Engine Package Imports
In `views.py`:
```python
from engine.ai_summary import get_cached_summary, is_ollama_available
from engine.bortle_lookup import lookup_bortle
from engine.forecast import _fetch_open_meteo, fetch_site_forecast
from engine.scorer import score_forecast, score_all
```

### Bortle Data Path
`engine/bortle_lookup.py` uses `Path(__file__).parent.parent.parent / "data" / "World_Atlas_2015.tif"` — climbs from `django/engine/` to repo root, then into `data/`.

### Cron Job (host crontab, travis user)
```
0 17 * * * docker compose exec -T django python manage.py compute_heatmap >> /var/log/starwolf-heatmap.log 2>&1
```

### CLAUDE.md Rules (important)
- Update `release_notes.json` after any user-facing change — run `TZ=America/Chicago date +%Y-%m-%d` for the correct date
- Update `docs/API_GUIDE.md` after any API contract change
- A stop hook fires if you end a turn with changed `.py`/`.html`/`.css` files but no release notes update

### Geocoding Background Process
After any Docker rebuild, restart with:
```bash
docker compose exec -d django python manage.py populate_site_locations
```

---

## Common Commands

```bash
# Health check
curl http://localhost:8080/django-health

# Rebuild and restart
docker compose build django && docker compose up -d

# Run heatmap manually
docker compose exec django python manage.py compute_heatmap

# Check logs
docker compose logs django --tail=50
```

---

## What's Not Done / Potential Next Steps

- `assets/starwolf-logo.svg` exists but is not wired into any template (favicon, nav brand image)
- No Django test suite exists yet — the old Streamlit tests are in `archive/`
- `requirements.txt` and `django/requirements-django.txt` are still two separate files; they could be merged into one
