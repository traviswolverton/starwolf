# Open-Meteo Forecast API — Stargazing Reference

> Free, no API key required. Non-commercial use up to 10,000 calls/day.
> Base URL: `https://api.open-meteo.com/v1/forecast`

---

## Sample API Call

```bash
curl "https://api.open-meteo.com/v1/forecast\
?latitude=29.37\
&longitude=-95.63\
&hourly=cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,\
visibility,relative_humidity_2m,lifted_index,cape,is_day\
&forecast_days=3\
&timezone=America/Chicago"
```

```python
import requests

params = {
    "latitude": 29.37,        # Brazos Bend State Park
    "longitude": -95.63,
    "hourly": [
        "cloud_cover",
        "cloud_cover_low",
        "cloud_cover_mid",
        "cloud_cover_high",
        "visibility",
        "relative_humidity_2m",
        "lifted_index",
        "cape",
        "is_day",
    ],
    "forecast_days": 3,
    "timezone": "America/Chicago",
}

resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
data = resp.json()
```

---

## Inputs (Query Parameters)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `latitude` | float | ✅ | WGS84 latitude of the observing site |
| `longitude` | float | ✅ | WGS84 longitude (negative for W hemisphere) |
| `hourly` | string array | ✅ | Comma-separated list of variables to return |
| `forecast_days` | int | No | Forecast horizon, 1–16 days (default: 7) |
| `timezone` | string | No | IANA timezone string, e.g. `America/Chicago` |
| `temperature_unit` | string | No | `celsius` (default) or `fahrenheit` |
| `wind_speed_unit` | string | No | `kmh` (default), `mph`, `ms`, `kn` |
| `past_days` | int | No | Include N days of past data in the response |

---

## Response Structure

```json
{
  "latitude": 29.372602,
  "longitude": -95.640305,
  "elevation": 20.0,
  "timezone": "America/Chicago",
  "timezone_abbreviation": "GMT-5",
  "generationtime_ms": 1.07,
  "utc_offset_seconds": -18000,
  "hourly_units": { ... },
  "hourly": {
    "time": ["2026-06-07T00:00", "2026-06-07T01:00", ...],
    "cloud_cover": [78, 3, 100, ...],
    ...
  }
}
```

### Top-Level Metadata

| Field | Description |
|---|---|
| `latitude` / `longitude` | Snapped coordinates (nearest model grid point) |
| `elevation` | Elevation of the grid cell in meters |
| `timezone` | IANA timezone used for the response |
| `timezone_abbreviation` | Short label, e.g. `GMT-5` |
| `utc_offset_seconds` | Offset from UTC in seconds |
| `generationtime_ms` | Server response time in milliseconds |
| `hourly_units` | Dictionary of variable names → unit strings |

---

## Hourly Variables — Stargazing Relevance

All `hourly` arrays are parallel arrays indexed by `time`. Every value corresponds to the hour indicated by the matching `time` entry.

---

### `time`
- **Unit:** ISO 8601 string (`2026-06-07T21:00`)
- **What it is:** Hourly timestamp in the requested timezone.
- **Usage:** Index into all other arrays. Filter on `is_day == 0` to isolate nighttime hours.

---

### `cloud_cover`
- **Unit:** % (0–100)
- **What it is:** Total sky coverage across all atmospheric layers combined.
- **Stargazing interpretation:**

| Value | Condition |
|---|---|
| 0–20% | ✅ Excellent — clear skies |
| 20–40% | 🟡 Good — some cloud breaks |
| 40–70% | 🟠 Marginal — patchy, frustrating |
| 70–100% | ❌ Bust |

- **Note:** Don't use this alone — 30% total cover is very different if it's all `cloud_cover_high` (thin cirrus) vs. `cloud_cover_low` (opaque stratus).

**Sample data (48h, Brazos Bend):**
```
2026-06-07T01:00 →   3%   ✅
2026-06-07T02:00 → 100%   ❌
2026-06-08T20:00 →  19%   ✅
2026-06-08T21:00 →  14%   ✅
2026-06-08T22:00 →   1%   ✅ ← best night window
```

---

### `cloud_cover_low`
- **Unit:** % (0–100)
- **What it is:** Low-level clouds (stratus, fog, cumulus) — roughly surface to 6,500 ft.
- **Stargazing interpretation:** The worst layer. Thick and opaque; if this is elevated, the night is over regardless of other conditions.

---

### `cloud_cover_mid`
- **Unit:** % (0–100)
- **What it is:** Mid-level clouds (altostratus, altocumulus) — roughly 6,500–20,000 ft.
- **Stargazing interpretation:** Also opaque but tends to move faster than low clouds. High values block the sky fully; moderate values may thin out.

---

### `cloud_cover_high`
- **Unit:** % (0–100)
- **What it is:** High-level cirrus and cirrostratus — ice crystal clouds above ~20,000 ft.
- **Stargazing interpretation:** The sneaky one. High cirrus looks invisible to the eye, but it kills transparency — faint galaxies, nebulae, and dim stars disappear. A night with `cloud_cover = 25%` but `cloud_cover_high = 25%` is likely much worse for DSO work than it appears.

---

### `visibility`
- **Unit:** meters
- **What it is:** Surface-level visibility, primarily reflecting aerosols, haze, humidity, smoke, and dust in the lower atmosphere.
- **Stargazing interpretation:**

| Value | Condition |
|---|---|
| > 20,000 m | ✅ Excellent transparency |
| 10,000–20,000 m | 🟡 Acceptable, some haze |
| < 10,000 m | 🟠 Noticeable sky glow and haze |
| < 5,000 m | ❌ Foggy/smoky, probably unusable |

- **Note:** In coastal Texas, Gulf moisture regularly suppresses this below 15,000 m even on clear nights. Watch for it.

---

### `relative_humidity_2m`
- **Unit:** % (0–100)
- **What it is:** Relative humidity at 2 meters above ground.
- **Stargazing interpretation:** Two concerns:
  1. **Dew risk** — as humidity climbs above ~85% and the air temperature approaches dewpoint, optics fog. A dew heater solves this but requires anticipating it.
  2. **Sky transparency** — high humidity loads the atmosphere with water vapor that scatters and absorbs light, degrading the limiting magnitude.

| Value | Risk |
|---|---|
| < 60% | ✅ Comfortable |
| 60–80% | 🟡 Monitor — dew possible later |
| > 80% | 🟠 Dew likely; plan accordingly |
| > 90% | ❌ Fog and fogged optics likely |

**Sample data:** The Brazos Bend 48h response shows 86–94% humidity during nighttime hours — typical for Houston-area summers. A dew heater is not optional here.

---

### `lifted_index`
- **Unit:** dimensionless (°C differential)
- **What it is:** Atmospheric stability index. Measures the temperature difference between a hypothetically lifted air parcel and the surrounding air at altitude. Positive = stable air, negative = unstable/convective.
- **Stargazing interpretation:** Your best proxy for **astronomical seeing** — whether stars will hold steady or boil at the eyepiece.

| Value | Seeing |
|---|---|
| > +5 | ✅ Excellent — rock-steady stars |
| +2 to +5 | ✅ Good |
| -1 to +2 | 🟡 Average |
| -3 to -1 | 🟠 Poor — noticeable shimmer |
| < -3 | ❌ Terrible — high convective instability |

**Sample data:** The 48h Brazos Bend response shows values of -3.3 to -8.9 throughout — consistently negative, indicating a highly unstable Gulf Coast atmosphere. This is normal for Texas summers; you won't get great planetary seeing, but wide-field DSO work under dark skies is still rewarding.

---

### `cape`
- **Unit:** J/kg (Joules per kilogram)
- **What it is:** Convective Available Potential Energy — the energy available to drive thunderstorm development. Correlates inversely with atmospheric stability.
- **Stargazing interpretation:** High CAPE means turbulent, convective atmosphere — bad for seeing, and a storm risk.

| Value | Risk |
|---|---|
| 0–500 J/kg | ✅ Low — stable |
| 500–1,500 J/kg | 🟡 Moderate — monitor |
| 1,500–3,000 J/kg | 🟠 High — unstable, storm possible |
| > 3,000 J/kg | ❌ Severe — significant storm risk |

**Sample data:** The Brazos Bend response shows 1,220–3,720 J/kg — elevated throughout, peaking at 3,720 during early morning hours. This is standard Texas summer fare. Pairs with the negative `lifted_index` to paint a consistent picture of an unstable atmosphere.

> **Tip:** `lifted_index` and `cape` tend to tell the same story. If they disagree, trust `lifted_index` for seeing assessment.

---

### `is_day`
- **Unit:** binary (0 or 1)
- **What it is:** 1 = daytime, 0 = nighttime, based on sunrise/sunset at the location.
- **Usage:** Filter all other arrays to nighttime-only hours before scoring:

```python
night_hours = [
    i for i, d in enumerate(data["hourly"]["is_day"]) if d == 0
]
```

---

## Interpreting the Sample Response

**Location:** 29.37°N, -95.63°W — Brazos Bend State Park area  
**Elevation:** 20 m  
**Period:** 2026-06-07 through 2026-06-08 (48 hours)

**Night 1 (Jun 7, 9pm–6am):** Largely socked in — `cloud_cover` at 100% for most hours, humidity 87–94%, CAPE 1,780–3,660 J/kg. Not a viable night.

**Night 2 (Jun 8, 9pm–midnight):** Improving window — `cloud_cover` drops to 1–14%, visibility climbs to 13,600–17,200 m, humidity still high (81–91%) but more manageable. Best hours: 10pm–midnight with `cloud_cover` of 1–9%.

---

## Composite Scoring (Proposed)

A simple 0–100 "Night Quality Score" derived from these variables:

```python
def score_hour(h: dict) -> float:
    score = 100.0
    score -= h["cloud_cover"] * 0.60          # Cloud cover is dominant (max -60)
    score -= max(0, -h["lifted_index"]) * 3   # Each degree of instability costs 3pts
    score -= max(0, h["cape"] - 500) / 100    # CAPE above 500 J/kg penalized
    score -= max(0, h["relative_humidity_2m"] - 70) * 0.3
    score -= max(0, (20000 - h["visibility"]) / 1000)
    return max(0, min(100, score))
```

| Score | Rating |
|---|---|
| 80–100 | ⭐⭐⭐⭐⭐ Exceptional |
| 60–79 | ⭐⭐⭐⭐ Good |
| 40–59 | ⭐⭐⭐ Marginal |
| 20–39 | ⭐⭐ Poor |
| 0–19 | ⭐ Stay home |

---

## Related APIs to Pair With

| Need | Source |
|---|---|
| Moon phase, rise/set times | `astral` Python library (local, no API) |
| Astronomy-specific seeing index | 7timer! (`http://www.7timer.info/bin/astro.php`) |
| Light pollution / Bortle class | Static Falchi et al. dataset (by lat/lon) |
| Meteor showers, planet positions | AstronomyAPI.com (free tier) |
