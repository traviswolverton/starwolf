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

## Setup

```bash
# Clone and install dependencies
git clone <repo>
cd stargazing-planner
pip install -r requirements.txt
```

### requirements.txt (planned)

```
requests
astral
pandas
sqlite3  # stdlib
```

---

## Project Status

Early planning / API exploration phase. Core scoring engine and CLI interface are next milestones.
