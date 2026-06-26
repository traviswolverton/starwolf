# Stargazing Trip Planner

A web app for planning optimal stargazing nights at dark-sky sites across the US. Pulls live weather and atmospheric data, combines it with moon phase calculations and astronomer-specific seeing forecasts, and scores each site/night combination so you can pick the best window for your trip.

Live instance: [starwolf.wolvertons.net](https://starwolf.wolvertons.net)
Source: [github.com/traviswolverton/starwolf](https://github.com/traviswolverton/starwolf)

> **Architecture note:** The app has been migrated from Streamlit to Django + HTMX (Phase 2 complete). Django runs on port 8080 alongside the legacy Streamlit app on port 8501. The Streamlit frontend will be retired in Phase 3 once routing is fully cut over. See [`prompts/django-migration-plan.md`](prompts/django-migration-plan.md) for status.

---

## Features

- Composite 0–100 night quality score per site per night
- Configurable scoring weights (cloud cover, moon, seeing, humidity)
- Hard disqualifier thresholds for cloud cover, precipitation probability, and visibility
- Astronomer-specific seeing and sky transparency from 7timer (1–8 scale)
- Moon phase, moonrise, and moonset calculations — fully offline via `astral`
- Up to 16-day hourly forecast from Open-Meteo (no API key required)
- Color-coded expandable result cards with per-metric breakdowns
- Calendar heatmap for comparing all sites across all nights at a glance
- Per-user settings (timezone, thresholds, unit system) stored in the database — persist across devices and sessions
- User location: geocode a home base to see distances to sites in results
- Proximity filter: score only sites within a configurable radius
- Imperial/metric toggle: distances and visibility threshold throughout the UI
- Role-based access control (guest / user / admin) via Cloudflare Access header auth
- Admin page for scoring weights and app-wide settings (requires admin role)
- Dual composite scores — telescope and naked eye — with Bortle class modifier
- Tonight's Forecast Map — color-coded heatmap of all 2,285+ sites scored for tonight
- REST API on port 8000 for programmatic access to the same forecast and scoring pipeline

---

## App Structure

```
stargazing-app/
├── django/                         # Django + HTMX frontend (port 8080) — primary
│   ├── config/                     # Django settings, URLs
│   ├── accounts/                   # User model, RBAC, auth middleware, management commands
│   │   └── management/commands/
│   │       ├── create_local_admin.py   # Create local admin (bypasses Cloudflare)
│   │       └── offboard_user.py        # Deactivate/reactivate users
│   ├── pages/                      # All page views
│   ├── templates/                  # Jinja2-style Django templates
│   └── static/css/main.css         # Single dark-theme stylesheet
├── Planner.py                      # Streamlit entry point (port 8501) — legacy, being retired
├── pages/                          # Streamlit pages — legacy
├── api.py                          # FastAPI REST API (port 8000) — kept as-is
├── forecast.py                     # Open-Meteo + 7timer API client (Redis-cached)
├── scorer.py                       # Composite night quality scorer
├── ai_summary.py                   # Ollama AI narrative summary generator
├── cache.py                        # Redis wrapper with silent fallback
├── db.py                           # PostgreSQL schema, seed data, SQLAlchemy engine
├── bortle_lookup.py                # World Atlas GeoTIFF Bortle class lookup
├── Dockerfile                      # Streamlit/shared app image
├── Dockerfile.django               # Django app image
├── docker-compose.yml              # django + app + api + postgres:16 + redis:7
└── API_GUIDE.md                    # Full REST API documentation
```

### Django Pages

| Page | URL | Purpose |
|------|-----|---------|
| **Planner** | `/planner` | Run forecast for nearby sites, ranked night cards, heatmap |
| **Sites** | `/sites` | Browse the 2,285+ site catalog with filters and distance sort |
| **Forecast Map** | `/heatmap` | Tonight's score for all sites as a Leaflet color-coded map |
| **Bortle** | `/bortle` | Look up Bortle class for any address or coordinates |
| **Location** | `/location` | Geocode a home base; drives distance display and proximity filter |
| **Preferences** | `/preferences` | Per-user timezone, thresholds, units — stored in DB, not session |
| **Admin** | `/admin-panel` | Scoring weights, app settings, Bortle fill (requires admin role) |
| **API** | `/api-guide` | Rendered API_GUIDE.md with live endpoint tabs |
| **Feedback** | `/feedback` | Submit bug reports / feature requests → GitHub issues |

### User Preferences

All settings are stored per-user in the `starwolf_user_preferences` table and loaded on every request — they persist across devices, browsers, and container restarts.

| Field | Default | Description |
|-------|---------|-------------|
| `units` | `metric` | `metric` or `imperial` — controls all distance and visibility display |
| `timezone` | `America/Chicago` | IANA timezone for night boundary calculations |
| `min_score_threshold` | 40 | Hide nights scoring below this |
| `disq_max_cloud_cover` | 85% | Hard disqualifier: cloud cover ceiling |
| `disq_max_precip_prob` | 40% | Hard disqualifier: precipitation probability ceiling |
| `disq_min_visibility_km` | 10 km | Hard disqualifier: visibility floor |
| `location_lat/lon` | None | Geocoded home base for distance display and proximity filter |

---

## Data Sources

| Data | Source | Coverage |
|------|--------|---------|
| Cloud cover, humidity, visibility, precipitation | [Open-Meteo](https://open-meteo.com) | Up to 16 days, hourly, free, no API key |
| Astronomical seeing + sky transparency | [7timer!](http://7timer.info) | ~3 days (72-hour limit of the free tier) |
| Moon phase / rise / set | `astral` Python library | Fully offline |
| Geocoding | [Nominatim/OSM](https://nominatim.org) + [Natural Resources Canada](https://geogratis.gc.ca) | Address → lat/lon |
| Dark-sky site catalog | [IDA / DarkSky International](https://darksky.org) | Importable via OSM Overpass API |

> **7timer note:** Seeing and transparency use a 1–8 scale where **1 is best**. Coverage is limited to approximately 3 days; nights beyond that will show `—` for these two fields — that's a hard limit of the data source.

---

## Scoring

### Composite Scores

Two 0–100 composites are computed per site per night using only nighttime hours (`is_day == 0` from Open-Meteo). Hours after midnight are assigned to the previous evening's night.

#### Telescope score

| Factor | Weight | Source |
|--------|--------|--------|
| Cloud cover (total) | 35% | Open-Meteo `cloud_cover` |
| Moon | 25% | `astral` (offline) |
| High cloud (cirrus) | 15% | Open-Meteo `cloud_cover_high` |
| Lifted Index (stability) | 15% | Open-Meteo `lifted_index` |
| Humidity | 10% | Open-Meteo `relative_humidity_2m` |

Telescope weights are stored in the `scoring_weights` table and editable by Admin.

#### Naked eye score

| Factor | Weight | Source |
|--------|--------|--------|
| Cloud cover (total) | 40% | Open-Meteo `cloud_cover` |
| Moon | 35% | `astral` (offline) |
| High cloud (cirrus) | 10% | Open-Meteo `cloud_cover_high` |
| Humidity | 10% | Open-Meteo `relative_humidity_2m` |
| Lifted Index (stability) | 5% | Open-Meteo `lifted_index` |

Naked eye weights are fixed constants (`NAKED_EYE_WEIGHTS` in `scorer.py`). After the weighted composite is calculated, a **Bortle class modifier** (0.55–1.0×) is applied based on the site's sky darkness rating to reflect light pollution impact on unaided viewing.

7timer seeing and transparency are displayed in result cards but do not affect either composite score.

### Hard Disqualifiers

Before scoring, each night is checked against three user-configurable thresholds (Preferences page). If any threshold is exceeded, the night is excluded from results entirely and moved to the "Disqualified nights" expander with a reason string.

### Interpreting Scores

| Score | Meaning |
|-------|---------|
| 70–100 | Worth the drive |
| 40–69 | Marginal — check individual factors |
| < 40 | Likely a bust |

---

## Data Model

All persistent state is stored in a PostgreSQL 16 database running as a Docker service. Three tables:

### `sites`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-assigned |
| `name` | TEXT | Display name |
| `lat` / `lon` | REAL | WGS84 coordinates |
| `bortle_class` | INTEGER | 1 (darkest) – 9 (inner city) |
| `elevation_m` | REAL | Elevation in metres |
| `notes` | TEXT | Free-form notes |
| `active` | INTEGER | Default active state for new sessions (1 = on, 0 = off) |

### `scoring_weights`

| Column | Type | Description |
|--------|------|-------------|
| `factor` | TEXT UNIQUE | Factor identifier (`cloud_cover`, `high_cloud`, `moon`, `lifted_index`, `humidity`) |
| `weight` | REAL | Fraction of the composite score (must sum to 1.00) |
| `description` | TEXT | Human-readable label |

### `app_settings`

Key/value pairs for admin-configurable application settings.

| Key | Default | Description |
|-----|---------|-------------|
| `forecast_days` | 10 | Forecast horizon in days (1–16) |
| `timezone` | `America/Chicago` | Default timezone |
| `min_score_threshold` | 40 | Default score threshold |
| `disq_max_cloud_cover` | 85 | Default cloud cover disqualifier |
| `disq_max_precip_prob` | 40 | Default precipitation probability disqualifier |
| `disq_min_visibility_km` | 10 | Default visibility disqualifier (km) |
| `planner_max_sites` | 250 | Maximum sites scored per Planner run; closest sites scored first when cap is hit |
| `ollama_url` | `http://localhost:11434` | Ollama endpoint for AI narrative summaries |
| `ollama_model` | `llama3` | Ollama model for AI summaries |

---

## REST API

The app exposes a scored forecast API on port 8000. See **[API_GUIDE.md](API_GUIDE.md)** for full documentation including parameters, response schema, curl/Python examples, and caching details.

```bash
# Quick example
curl "http://localhost:8000/v1/forecast?lat=30.67&lon=-104.02&days=7&bortle_class=2"

# Interactive docs
open http://localhost:8000/docs
```

---

## External Data Sources

### Open-Meteo

**Endpoint:** `GET https://api.open-meteo.com/v1/forecast`  
No API key required. Free for non-commercial use.

**Parameters used:**

```python
params = {
    "latitude":  29.37,
    "longitude": -95.63,
    "hourly": [
        "cloud_cover", "cloud_cover_high",
        "visibility", "relative_humidity_2m",
        "lifted_index", "precipitation_probability", "is_day",
    ],
    "forecast_days": 10,
    "timezone": "America/Chicago",
}
```

**Key response fields:**

| Variable | Unit | Description |
|----------|------|-------------|
| `cloud_cover` | % | Total sky coverage |
| `cloud_cover_high` | % | Cirrus — kills transparency even at low total cover |
| `lifted_index` | °C | Atmospheric stability; positive = stable = good seeing |
| `relative_humidity_2m` | % | Above ~85%, dew on optics is likely |
| `visibility` | m | Surface haze/smoke; below 10 km starts to matter |
| `precipitation_probability` | % | Rain probability per hour |
| `is_day` | 0/1 | 0 = nighttime — used to isolate scoring hours |

### 7timer (ASTRO product)

**Endpoint:** `GET http://www.7timer.info/bin/api.pl?lon=&lat=&product=astro&output=json`  
No API key required. Free service. Coverage: ~72 hours (24 × 3-hour slots).

**Key response fields (1–8 scale, 1 = best):**

| Field | Description |
|-------|-------------|
| `seeing` | Atmospheric steadiness — critical for planetary/high-mag work |
| `transparency` | Sky clarity/darkness — critical for faint DSO work |

---

## Code Reference

### `forecast.py`

- `fetch_site_forecast(site: dict, forecast_days: int, timezone: str) -> dict` — fetches Open-Meteo + 7timer for one site
- `fetch_all_forecasts() -> list[dict]` — fetches all active sites from the DB (used for standalone runs)

### `scorer.py`

- `score_forecast(forecast: dict, tz_str: str, disqualifiers: dict | None) -> list` — scores all nights in one site's forecast
- `score_all(forecasts: list, tz_str: str, disqualifiers: dict | None) -> list` — scores all sites, sorted by date then score (desc)
- `NAKED_EYE_WEIGHTS` — dict of fixed naked eye factor weights

Each scored night dict:
```python
{
    "site":       "Enchanted Rock SP",
    "date":       "2026-06-27",
    "composite":  88.0,    # telescope score
    "naked_eye":  82.3,    # naked eye score, Bortle-adjusted
    "factors":    {"cloud_cover": 100.0, "high_cloud": 100.0, "moon": 99.7, ...},
    "stats": {
        "avg_cloud_cover":     0.0,
        "avg_high_cloud":      0.0,
        "avg_humidity":        77.9,
        "avg_lifted_index":   -2.5,
        "night_hours":         9,
        "seeing_7timer":       3.2,   # None if beyond 7timer range
        "transparency_7timer": 4.0,
        "bortle_class":        2,     # None if not set on the site
    },
    # Only present if disqualified:
    "disqualified": "Cloud cover 91% > 85% limit",
}
```

### `utils.py`

Shared helpers used across all pages:

| Function | Description |
|----------|-------------|
| `init_session_settings()` | Seed all session state keys from DB defaults on first page load |
| `sync_site_active()` | Sync `site_active` dict with DB; preserves per-session overrides |
| `render_sidebar()` | Display user location (or "set location" link) at sidebar bottom |
| `dist_display(km)` | Format a km value as `"43 km"` or `"27 mi"` per session units |
| `dist_unit()` | Returns `"km"` or `"mi"` |
| `km_to_display(km)` | Convert km to display-unit float |
| `display_to_km(val)` | Convert display-unit float back to km |

---

## Setup

### Prerequisites

- [Docker](https://docs.docker.com/engine/install/) with the Compose plugin
- Your user in the `docker` group: `sudo usermod -aG docker $USER && newgrp docker`

### 1. Clone and configure secrets

```bash
git clone https://github.com/traviswolverton/starwolf
cd starwolf
```

Create `.streamlit/secrets.toml` (git-ignored):
```toml
admin_password = "your-admin-password"
github_token   = "your-github-token"   # fine-grained PAT, Issues: Read & Write
```

### 2. Start the stack

```bash
docker compose up -d
```

This starts five containers:
- **django** — Django + HTMX on port 8080 (primary frontend)
- **app** — Streamlit on port 8501 (legacy, being retired)
- **api** — FastAPI / uvicorn on port 8000
- **db** — PostgreSQL 16 (data in `postgres_data` Docker volume)
- **redis** — Redis 7 (data in `redis_data` Docker volume)

### 3. Create a local admin user

```bash
cd /opt/stargazing-app
docker compose exec django python manage.py create_local_admin admin@example.com yourpassword
```

This creates an admin user that can log in at `/accounts/login/` without going through Cloudflare Access — useful for local dev and emergency access.

### 4. Verify

```bash
docker compose ps
curl localhost:8080/django-health    # should return: {"status":"ok"}
curl localhost:8000/healthz          # should return: {"status":"ok"}
```

Opens at `http://localhost:8080`.

### User management

```bash
# Deactivate a user removed from Cloudflare Access (preserves their preferences)
docker compose exec django python manage.py offboard_user someone@example.com

# Re-activate them if re-added to Cloudflare
docker compose exec django python manage.py offboard_user someone@example.com --reactivate
```

### Updating

```bash
git pull
docker compose up -d --build   # rebuilds the app image, leaves db/redis untouched
```

### Environment variables

| Variable | Set in | Description |
|----------|--------|-------------|
| `DATABASE_URL` | `docker-compose.yml` | PostgreSQL connection string |
| `REDIS_URL` | `docker-compose.yml` | Redis connection string |
| `ADMIN_PASSWORD` | `.streamlit/secrets.toml` | Admin page password (fallback to env var) |

### Caching

API responses are cached in Redis automatically:

| Source | TTL | Cache key |
|--------|-----|-----------|
| Open-Meteo | 1 hour | `openmeteo:{lat}:{lon}:{days}:{tz}` |
| 7timer | 3 hours | `7timer:{lat}:{lon}` |

Cache is **transparent** — if Redis is unreachable the app falls back to live API calls without erroring.

Inspect cache keys after a forecast run:
```bash
docker compose exec redis redis-cli keys "*"
```

### Data persistence

Postgres and Redis data live in named Docker volumes and survive container restarts. They are only removed if you explicitly run `docker compose down -v`.

### Migrating from SQLite

If upgrading from a previous SQLite-based install:
```bash
# Expose Postgres port temporarily (add ports: ["5432:5432"] to db in docker-compose.yml)
docker compose up -d

DATABASE_URL=postgresql://stargazing:stargazing@localhost:5432/stargazing \
    python migrate_sqlite_to_postgres.py
```
