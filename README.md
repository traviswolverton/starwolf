# Stargazing Trip Planner

A multi-user Streamlit web app for planning optimal stargazing nights at dark-sky sites. Pulls live weather and atmospheric data, combines it with moon phase calculations and astronomer-specific seeing forecasts, and scores each site/night combination so you can pick the best window for your trip.

Live instance: [starwolf.wolvertons.net](https://starwolf.wolvertons.net)
Source: [gitea.wolvertons.net/travis/stargazing-app](https://gitea.wolvertons.net/travis/stargazing-app)

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
- Session-based per-user settings (timezone, thresholds, unit system) — no login required
- User location: geocode a home base to see distances to sites in results
- Site database: add, edit, deactivate sites; import from IDA dark-sky catalog or by address
- Proximity filter: activate all sites within a configurable radius of any location
- Imperial/metric toggle: distances and visibility threshold throughout the UI
- Password-protected Admin page for scoring weights and app-wide settings

---

## App Structure

The app is a Streamlit multi-page app. Entry point: `Planner.py`.

```
stargazing-app/
├── Planner.py            # Main forecast page (entry point)
├── pages/
│   ├── 0_Location.py     # Set/clear user home location
│   ├── 1_Sites.py        # Site catalog management
│   ├── 2_Preferences.py  # Per-session user settings
│   └── 3_Admin.py        # Password-gated admin panel
├── forecast.py           # Open-Meteo + 7timer API client
├── scorer.py             # Composite night quality scorer
├── db.py                 # SQLite schema, seed data, helpers
├── utils.py              # Shared session state + sidebar helpers
├── osm_import.py         # Geocoding + IDA dark-sky site importer
├── run.sh                # Dev launcher
└── stargazing.db         # SQLite database (git-ignored)
```

### Pages

| Page | Purpose |
|------|---------|
| **Planner** | Run forecast, view ranked result cards and heatmap |
| **Location** | Geocode a home location; drives distance display and proximity filter |
| **Sites** | Manage the site catalog — activate/deactivate, add by address, import from IDA |
| **Preferences** | Session timezone, min score threshold, hard disqualifiers, unit system |
| **Admin** | Password-gated; scoring weights and app-wide settings (forecast horizon, etc.) |

### Session State

All user-facing settings are stored per-session in `st.session_state` — multiple users can use the app simultaneously without affecting each other. Nothing is written to the database except by the Admin page.

| Key | Default | Description |
|-----|---------|-------------|
| `timezone` | `America/Chicago` | IANA timezone for night boundary calculations |
| `min_score_threshold` | 40 | Hide nights scoring below this |
| `disq_max_cloud_cover` | 85% | Hard disqualifier: cloud cover ceiling |
| `disq_max_precip_prob` | 40% | Hard disqualifier: precipitation probability ceiling |
| `disq_min_visibility_km` | 10 km | Hard disqualifier: visibility floor (stored in km) |
| `units` | `metric` | `"metric"` or `"imperial"` — controls distance/visibility display |
| `user_location` | `None` | Dict: `{text, lat, lon, display}` from geocoder |
| `site_active` | DB defaults | Dict of `{site_id: bool}` — overrides DB `active` column per session |

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

### Composite Score

A weighted 0–100 composite is computed per site per night using only nighttime hours (`is_day == 0` from Open-Meteo). Hours after midnight are assigned to the previous evening's night.

| Factor | Weight | Source |
|--------|--------|--------|
| Cloud cover (total) | 35% | Open-Meteo `cloud_cover` |
| High cloud (cirrus) | 15% | Open-Meteo `cloud_cover_high` |
| Moon | 25% | `astral` (offline) |
| Lifted Index (stability) | 15% | Open-Meteo `lifted_index` |
| Humidity | 10% | Open-Meteo `relative_humidity_2m` |

Weights are stored in the `scoring_weights` table and editable by Admin. 7timer seeing and transparency are displayed in result cards but do not affect the composite score.

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

All persistent configuration is stored in a local SQLite database (`stargazing.db`, git-ignored). Three tables:

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
| `timezone` | `America/Chicago` | Default timezone for new sessions |
| `min_score_threshold` | 40 | Default score threshold for new sessions |
| `disq_max_cloud_cover` | 85 | Default cloud cover disqualifier |
| `disq_max_precip_prob` | 40 | Default precipitation probability disqualifier |
| `disq_min_visibility_km` | 10 | Default visibility disqualifier (km) |

---

## API Reference

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

Each scored night dict:
```python
{
    "site":      "Enchanted Rock SP",
    "date":      "2026-06-27",
    "composite": 88.0,
    "factors":   {"cloud_cover": 100.0, "high_cloud": 100.0, "moon": 99.7, ...},
    "stats": {
        "avg_cloud_cover":     0.0,
        "avg_high_cloud":      0.0,
        "avg_humidity":        77.9,
        "avg_lifted_index":   -2.5,
        "night_hours":         9,
        "seeing_7timer":       3.2,   # None if beyond 7timer range
        "transparency_7timer": 4.0,
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

```bash
git clone https://gitea.wolvertons.net/travis/stargazing-app
cd stargazing-app
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Admin password** (optional): create `.streamlit/secrets.toml`:
```toml
admin_password = "your-password-here"
```

If not set, the Admin page falls back to the `ADMIN_PASSWORD` environment variable, then allows open access.

**Run:**
```bash
./run.sh
# or
streamlit run Planner.py
```

Opens at `http://localhost:8501`.

**Production (systemd):**
```ini
[Unit]
Description=Stargazing Trip Planner
After=network.target

[Service]
Type=simple
User=travis
WorkingDirectory=/opt/stargazing-app
ExecStart=/opt/stargazing-app/venv/bin/streamlit run Planner.py --server.port 8501 --server.headless true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The SQLite database (`stargazing.db`) is created and seeded on first run. It is git-ignored.
