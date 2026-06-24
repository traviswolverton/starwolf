# Stargazing Forecast API Guide

The app exposes a REST API on port **8000** that runs the same scoring pipeline as the Streamlit UI. You can query any lat/lon with any date range and get back telescope and naked eye scores for every upcoming night.

Interactive docs (OpenAPI / Swagger UI): `http://localhost:8000/docs`

---

## Base URL

```
http://localhost:8000
```

In production substitute your host, e.g. `http://starwolf.wolvertons.net:8000`.

---

## Endpoints

### `GET /v1/forecast`

Score upcoming nights at a given location.

#### Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `lat` | float | ✅ | — | Latitude (−90 to 90) |
| `lon` | float | ✅ | — | Longitude (−180 to 180) |
| `days` | int | | `7` | Forecast horizon in days (1–16) |
| `timezone` | string | | App setting | IANA timezone string (e.g. `America/Chicago`). Defaults to the value stored in the app's DB settings. |
| `bortle_class` | int | | `null` | Bortle class 1–9. When supplied, applies a multiplier (0.55–1.0×) to the naked eye score. Omit for no penalty. |

#### Response

```json
{
  "lat": 30.67,
  "lon": -104.02,
  "timezone": "America/Chicago",
  "days": 7,
  "nights": [
    {
      "site": "30.6700,-104.0200",
      "date": "2026-07-01",
      "composite": 81.4,
      "naked_eye": 75.8,
      "factors": {
        "cloud_cover":  95.0,
        "high_cloud":   90.0,
        "moon":         82.3,
        "lifted_index": 66.7,
        "humidity":     62.5
      },
      "stats": {
        "avg_cloud_cover":       5.0,
        "avg_high_cloud":        10.0,
        "avg_humidity":          55.0,
        "avg_lifted_index":      0.25,
        "night_hours":           9,
        "seeing_7timer":         3.0,
        "transparency_7timer":   4.0,
        "bortle_class":          2
      },
      "disqualified": null
    }
  ],
  "errors": []
}
```

#### Field notes

| Field | Description |
|---|---|
| `composite` | Telescope score 0–100. Weighted from cloud cover, high cloud, moon, stability, and humidity. |
| `naked_eye` | Naked eye score 0–100. Same factors, different weights, Bortle modifier applied. |
| `factors` | Per-factor 0–100 scores used to build `composite`. All factors are always present. |
| `stats.seeing_7timer` | Atmospheric steadiness from 7timer (1–8, 1 = best). `null` beyond ~3 days. |
| `stats.transparency_7timer` | Sky clarity from 7timer (1–8, 1 = best). `null` beyond ~3 days. |
| `stats.bortle_class` | Echoes the `bortle_class` query param; `null` if not supplied. |
| `disqualified` | Always `null` from the API — no threshold filtering is applied. All nights are returned. |
| `errors` | Non-empty if Open-Meteo or 7timer failed. Score data may still be partial. |

#### Score bands

| Score | Meaning |
|---|---|
| 70–100 | Worth the drive |
| 40–69 | Marginal — check individual factors |
| < 40 | Likely a bust |

---

### `GET /healthz`

Health check. Returns `{"status": "ok"}` when the API is running.

---

## Caching

API responses share the same Redis cache as the Streamlit app:

| Source | TTL | Cache key |
|---|---|---|
| Open-Meteo | 1 hour | `openmeteo:{lat}:{lon}:{days}:{tz}` |
| 7timer | 3 hours | `7timer:{lat}:{lon}` |

If you call the API for the same coordinates within the TTL window, the response is served from cache and returns immediately. The Streamlit app and API share the cache, so a forecast run in the UI warms the cache for subsequent API calls at the same coordinates.

---

## Scoring weights

The two scores use different factor weights:

| Factor | 🔭 Telescope | 👁 Naked Eye |
|---|---|---|
| Cloud Cover | 35% | 40% |
| Moon | 25% | 35% |
| High Cloud | 15% | 10% |
| Stability (LI) | 15% | 5% |
| Humidity | 10% | 10% |

Telescope weights are stored in the database and can be adjusted by an admin. Naked eye weights are fixed constants. Seeing and transparency (7timer) are displayed in the UI and stats payload but do not contribute to either composite.

The **Bortle modifier** is applied multiplicatively to the naked eye composite:

| Bortle class | Modifier |
|---|---|
| 1–2 | 1.00 (no penalty) |
| 3 | 0.92 |
| 4 | 0.84 |
| 5 | 0.75 |
| 6 | 0.70 |
| 7 | 0.65 |
| 8 | 0.60 |
| 9 | 0.55 |

---

## Examples

### curl

```bash
# Basic — 7 days at McDonald Observatory area, Bortle 2
curl "http://localhost:8000/v1/forecast?lat=30.67&lon=-104.02&bortle_class=2"

# Longer window in a specific timezone
curl "http://localhost:8000/v1/forecast?lat=36.10&lon=-112.11&days=14&timezone=America/Phoenix"

# Health check
curl "http://localhost:8000/healthz"
```

### Python

```python
import requests

resp = requests.get(
    "http://localhost:8000/v1/forecast",
    params={
        "lat": 30.67,
        "lon": -104.02,
        "days": 10,
        "bortle_class": 2,
        "timezone": "America/Chicago",
    },
    timeout=30,
)
resp.raise_for_status()
data = resp.json()

for night in data["nights"]:
    print(
        f"{night['date']}"
        f"  🔭 {night['composite']:.0f}"
        f"  👁 {night['naked_eye']:.0f}"
        f"  cloud={night['stats']['avg_cloud_cover']}%"
    )
```

### Filter to best nights client-side

```python
good_nights = [n for n in data["nights"] if n["composite"] >= 70]
```

---

## Running the API

The API runs as a separate Docker service using the same image as the Streamlit app:

```bash
# Start everything
docker compose up -d

# API only (if app + db + redis are already running)
docker compose up -d api

# Rebuild after code changes
docker compose up -d --build api

# Logs
docker compose logs -f api
```

The API and the Streamlit app share the same Docker image — `api.py` simply overrides the container command to run `uvicorn` instead of `streamlit`.
