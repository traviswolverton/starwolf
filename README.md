# 🔭 Stargazing Trip Planner

A Python app for planning optimal stargazing nights at dark-sky sites across Texas. Pulls live weather and atmospheric data, combines it with moon phase and light pollution information, and scores each site/night combination so you can pick the best window for your trip.

---

## Features

- Hourly cloud cover forecasts (total, low, mid, and high layers) for up to 16 days out
- Atmospheric seeing proxies (Lifted Index, CAPE) to predict star steadiness
- Moon phase, moonrise, and moonset calculations — entirely offline
- Composite "night quality" score per site per night
- Pre-loaded database of known Texas dark-sky sites
- Humidity and dew risk alerts (protect your optics)

---

## Data Sources

| Data | Source | Notes |
|------|--------|-------|
| Cloud cover + atmospheric forecast | [Open-Meteo](https://open-meteo.com) | Free, no API key, up to 16-day forecast |
| Astronomy-specific seeing | [7timer!](http://www.7timer.info) | Free, no key, purpose-built for astronomers |
| Moon phase / rise / set | `astral` Python library | Fully local, no API call |
| Light pollution / Bortle class | Falchi et al. static dataset | Load once, query by coordinates |
| Known TX dark-sky sites | Local SQLite database | Manually curated |

---

## Open-Meteo API

### Endpoint

```
GET https://api.open-meteo.com/v1/forecast
```

No API key required. Free for non-commercial use.

### Sample Request

```python
import requests

params = {
    "latitude": 29.37,       # Brazos Bend State Park
    "longitude": -95.63,
    "hourly": [
        "cloud_cover",
        "cloud_cover_low",
        "cloud_cover_mid",
        "cloud_cover_high",
        "visibility",
        "relative_humidity_2m",
        "dewpoint_2m",
        "lifted_index",
        "cape",
        "wind_speed_10m",
        "precipitation_probability",
        "is_day",
    ],
    "forecast_days": 10,
    "timezone": "America/Chicago",
}

resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
data = resp.json()
```

### Response Variables

All fields are returned as hourly arrays aligned to the `time` array.

#### Cloud Cover

| Variable | Unit | Description |
|----------|------|-------------|
| `cloud_cover` | % | Total sky coverage. Under 20% is good; over 50% is likely a bust. |
| `cloud_cover_low` | % | Stratus and fog (surface–6,500 ft). Thick and opaque — worst for stargazing. |
| `cloud_cover_mid` | % | Altostratus (6,500–20,000 ft). Opaque but can move through faster. |
| `cloud_cover_high` | % | Cirrus (20,000+ ft). Thin ice clouds that kill transparency even at low total cover %. |

> **Note:** Don't rely on `cloud_cover` alone. A night showing 30% total cover that's all `cloud_cover_high` will still wash out faint nebulae.

#### Atmospheric Seeing

| Variable | Unit | Description |
|----------|------|-------------|
| `lifted_index` | °C | Atmospheric stability. Positive = stable = good seeing. Aim for > +3. Negative = turbulent, stars will boil. |
| `cape` | J/kg | Convective energy. 0–500 = low risk; 500–2000 = moderate; >2000 = significant storm/turbulence potential. |

> In Houston/Gulf Coast summers, `lifted_index` is routinely −3 to −9 and CAPE 1,500–3,700 J/kg. This is normal. It limits high-magnification planetary work but wide-field DSO sessions are still very viable under a dark sky.

#### Humidity & Dew Risk

| Variable | Unit | Description |
|----------|------|-------------|
| `relative_humidity_2m` | % | Above ~85%, dew on eyepieces and corrector plates is likely. Bring a dew heater. |
| `dewpoint_2m` | °C | If air temperature approaches dewpoint, optics will fog. |

#### Visibility & Precipitation

| Variable | Unit | Description |
|----------|------|-------------|
| `visibility` | m | Surface haze, smoke, or dust. Below 10,000 m starts to matter; below 5,000 m is rough. |
| `precipitation_probability` | % | Rain probability for that hour. |
| `wind_speed_10m` | km/h | Surface wind. Strong wind can cause image blur through scope shake. |

#### Utility

| Variable | — | Description |
|----------|---|-------------|
| `is_day` | 0/1 | 0 = nighttime, 1 = daytime. Use to filter arrays down to hours that matter. |
| `time` | ISO 8601 | Timestamp for each hourly slot. All other arrays index against this. |

### Response Metadata

| Field | Description |
|-------|-------------|
| `latitude` / `longitude` | Snapped coordinates (nearest grid point) |
| `elevation` | Elevation in meters at that grid point |
| `timezone` | Timezone used for `time` array |
| `hourly_units` | Dictionary of units for each requested variable |

---

## Night Quality Scoring (Proposed)

A composite 0–100 score per site/night, weighted roughly as follows:

| Factor | Weight | Ideal Value |
|--------|--------|-------------|
| Cloud cover (total) | 35% | < 20% |
| High cloud cover | 15% | < 10% |
| Moon illumination + hours above horizon | 25% | New moon, sets early |
| Lifted Index (seeing) | 15% | > +3 |
| Humidity / dew risk | 10% | < 70% RH |

Scores above ~70 are worth the drive. Below 40 is probably a bust.

---

## Texas Dark-Sky Sites (Initial Database)

| Site | Lat | Lon | Notes |
|------|-----|-----|-------|
| Brazos Bend State Park | 29.37 | −95.63 | Closest dark site to Houston; alligators |
| McDonald Observatory area | 30.67 | −104.02 | Best Bortle in TX; 6+ hr drive |
| Balmorhea State Park | 30.95 | −103.77 | Near McDonald; excellent |
| Sam Houston National Forest | 30.75 | −95.50 | Moderate dark sky, closer option |
| Enchanted Rock SP | 30.50 | −98.82 | Good Hill Country site |

---

## Data Model

All configuration is stored in a local SQLite database (`stargazing.db`, git-ignored). Three tables:

### `sites`
One row per dark-sky observing location.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-assigned |
| `name` | TEXT | Display name |
| `lat` / `lon` | REAL | WGS84 coordinates |
| `bortle_class` | INTEGER | 1 (darkest) – 9 (inner city) |
| `elevation_m` | REAL | Elevation in metres |
| `notes` | TEXT | Free-form notes |
| `active` | INTEGER | 1 = included in forecasts, 0 = hidden |

### `scoring_weights`
One row per scoring factor. Weights must sum to 1.00.

| Column | Type | Description |
|--------|------|-------------|
| `factor` | TEXT UNIQUE | Factor identifier (e.g. `cloud_cover`) |
| `weight` | REAL | Fraction of the 0–100 score (0.0–1.0) |
| `description` | TEXT | Human-readable explanation |

Default factors: `cloud_cover` (0.35), `high_cloud` (0.15), `moon` (0.25), `lifted_index` (0.15), `humidity` (0.10).

### `app_settings`
Key/value pairs for application-wide settings.

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT PK | Setting name |
| `value` | TEXT | Setting value (always stored as text) |
| `description` | TEXT | Human-readable explanation |

Default keys: `forecast_days`, `timezone`, `min_score_threshold`.

---

## App

Everything runs from a single Streamlit app:

```bash
streamlit run admin.py
```

Opens at `http://localhost:8501`. Four tabs:

| Tab | Purpose |
|-----|---------|
| **Forecast** | Ranked list of best nights + calendar heatmap. Auto-fetches on load, caches for 1 hour. Refresh button to force a new fetch. |
| **Dark-Sky Sites** | Add/edit/deactivate observing sites. |
| **Scoring Weights** | Adjust factor weights (must sum to 1.00). |
| **App Settings** | Forecast horizon, timezone, score threshold. |

The database is created and seeded with Texas dark-sky sites and default weights on first run.

---

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Forecast Fetcher

`forecast.py` fetches live data for all active sites from the database.

**Public API:**
- `fetch_site_forecast(site: dict) -> dict` — fetches Open-Meteo + 7timer for one site
- `fetch_all_forecasts() -> list[dict]` — fetches all active sites from the DB

Each result dict contains:
```python
{
    "site":        {...},   # site record from DB
    "open_meteo":  {...},   # raw Open-Meteo hourly response
    "seven_timer": {...},   # raw 7timer dataseries response
    "errors":      [...],   # per-source error strings (empty on success)
}
```

Forecast horizon and timezone are read from `app_settings` in the database (`forecast_days`, `timezone`). A failed source populates `errors` and leaves its key as `None` — the other source is still returned.

Run standalone to verify connectivity against all active sites:
```bash
python forecast.py
```

---

## Scoring Engine

`scorer.py` converts raw forecast data into a 0–100 night quality score per site per night.

**Public API:**
- `score_forecast(forecast: dict) -> list` — scores all nights in one site's forecast
- `score_all(forecasts: list) -> list` — scores all sites, sorted by date then score (desc)

Each result dict contains:
```python
{
    "site":      "Enchanted Rock SP",
    "date":      "2026-06-27",
    "composite": 88.0,
    "factors": {
        "cloud_cover":  100.0,  # 0–100 per factor
        "high_cloud":   100.0,
        "moon":          99.7,
        "lifted_index":  50.2,
        "humidity":      55.2,
    },
    "stats": {
        "avg_cloud_cover":  0.0,
        "avg_high_cloud":   0.0,
        "avg_humidity":     77.9,
        "avg_lifted_index": -2.5,
        "night_hours":      9,
        "seeing_7timer":    3.2,       # 1–8 scale; None if beyond 7timer range
        "transparency_7timer": 4.0,    # 1–8 scale
    }
}
```

**Factor scoring:**

| Factor | Source | Ideal → 100 pts |
|--------|--------|-----------------|
| `cloud_cover` | Open-Meteo `cloud_cover` avg | 0% cloud |
| `high_cloud` | Open-Meteo `cloud_cover_high` avg | 0% high cirrus |
| `moon` | `astral` library (offline) | New moon, sets before dark |
| `lifted_index` | Open-Meteo `lifted_index` avg | +5°C or above |
| `humidity` | Open-Meteo `relative_humidity_2m` avg | Below 60% RH |

Weights are read from the `scoring_weights` table and must sum to 1.00. 7timer seeing and transparency are included in `stats` as supplemental info but do not affect the composite score.

Nighttime hours are identified via Open-Meteo's `is_day == 0` flag. Hours after midnight are assigned to the previous evening's night.

Run standalone to print the top 5 nights across all active sites:
```bash
python scorer.py
```

---

## Project Status

Data model, configuration UI, forecast fetcher, and scoring engine complete. Next milestone: CLI interface.
