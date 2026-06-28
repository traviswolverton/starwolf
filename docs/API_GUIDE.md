# Stargazing Forecast API Guide

The app exposes a REST API that runs the same scoring pipeline as the web UI. You can query any lat/lon with any date range and get back telescope and naked eye scores for every upcoming night.

---

## Base URL

```
https://starwolf.wolvertons.net/api   # production
```

---

## Endpoints

### `GET /v1/bortle` — Bortle Class Lookup

Returns the Bortle class and sky quality meter (SQM) reading for any lat/lon, derived from the Falchi et al. 2016 World Atlas of Artificial Night Sky Brightness.

#### Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `lat` | float | ✅ | Latitude (−90 to 90) |
| `lon` | float | ✅ | Longitude (−180 to 180) |

#### Response

```json
{
  "bortle": 2,
  "sqm": 21.94
}
```

#### Field notes

| Field | Description |
|---|---|
| `bortle` | Bortle class 1–9. 1 = pristine dark sky; 9 = inner-city sky. |
| `sqm` | Sky Quality Meter reading in mag/arcsec². Higher = darker. |

#### Error responses

| Status | When |
|---|---|
| `422` | Coordinates are outside the raster extent or have no data. |
| `503` | World Atlas GeoTIFF is not mounted on this server. |

---

### `GET /v1/sites` — Bulk Site Export

Returns all sites in the catalog with their full metadata. No parameters. Always returns every site regardless of active status.

#### Response

```json
{
  "count": 42,
  "sites": [
    {
      "id":           100,
      "name":         "Big Bend Ranch State Park",
      "lat":          29.4,
      "lon":          -103.75,
      "bortle_class": 1,
      "elevation_m":  null,
      "notes":        "Bortle 1; darkest skies in Texas ...",
      "active":       1,
      "site_type":    "ida_certified"
    }
  ]
}
```

#### Field notes

| Field | Description |
|---|---|
| `id` | Stable integer primary key. |
| `bortle_class` | 1–9 light pollution scale; `null` if unknown. |
| `elevation_m` | Elevation in metres; `null` if not recorded. |
| `active` | `1` = included in UI forecasts by default; `0` = hidden. |
| `site_type` | One of: `ida_certified`, `tx_state_park`, `national_park`, `national_forest`, `observatory`, `private`, `community`. `null` if unclassified. |

---

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
      "seven_timer_tier": {
        "tier":         "excellent",
        "score":        80.7,
        "seeing":       3.0,
        "transparency": 4.0
      }
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
| `seven_timer_tier.tier` | Blended 7timer quality: `"excellent"` (≥70), `"good"` (40–69), `"mediocre"` (<40), or `"no_data"` when 7timer is unavailable. |
| `seven_timer_tier.score` | Blended 0–100 value (65% seeing + 35% transparency, both inverted from the 1–8 scale). `null` when `tier` is `"no_data"`. |
| `seven_timer_tier.seeing` | Same as `stats.seeing_7timer`. Included for convenience. |
| `seven_timer_tier.transparency` | Same as `stats.transparency_7timer`. Included for convenience. |
| `errors` | Non-empty if 7timer failed. Open-Meteo failures produce a 502 instead (see below). |

#### Error responses

| Status | When |
|---|---|
| `422 Unprocessable Entity` | A parameter failed validation — `lat`/`lon` out of range, `days` outside 1–16, etc. FastAPI returns a structured `detail` array. |
| `502 Bad Gateway` | Open-Meteo is unreachable or returned an error. The `detail` field contains the reason (e.g. `"Open-Meteo: Latitude must be in range of -90 to 90°"`). |

7timer failures are treated as soft errors — the response still returns with HTTP 200, scored nights are included, and `errors[]` contains the 7timer error string. Seeing, transparency, and `seven_timer_tier` will show `null` / `"no_data"` for all nights.

#### Score bands

| Score | Meaning |
|---|---|
| 70–100 | Worth the drive |
| 40–69 | Marginal — check individual factors |
| < 40 | Likely a bust |

---

### `GET /sites/<id>/sky` — Sky Object Visibility (What's Up?)

Returns everything visible in the sky for a specific site on a given date. Requires authentication (session cookie). Used by the site detail page "What's Up?" section via HTMX.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `date` | string | today | `YYYY-MM-DD`. Clamped to today + 10 days. |

**Response** — HTML partial (`_sky_objects.html`), not JSON. Intended for HTMX consumption.

**Cache** — `sky:{site_id}:{date}:{equipment}:{bortle}` → 1 hour TTL in Redis.

---

### `GET /tonight` — Tonight's Sky (Location-Based)

Standalone page showing sky visibility for the authenticated user's saved location. Fetches a live forecast score from the same pipeline as the Planner to provide a conditions banner alongside the astronomical data.

Not a JSON endpoint — returns a full HTML page.

---

### `GET /healthz`

Health check. Returns `{"status": "ok"}` when the API is running.

---

## Caching

API responses share the same Redis cache as the web app:

| Source | TTL | Cache key |
|---|---|---|
| Open-Meteo | 1 hour | `openmeteo:{lat}:{lon}:{days}:{tz}` |
| 7timer | 3 hours | `7timer:{lat}:{lon}` |

If you call the API for the same coordinates within the TTL window, the response is served from cache and returns immediately. A forecast run in the web UI warms the cache for subsequent API calls at the same coordinates.

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

Both telescope and naked eye weights are stored in the database and can be adjusted by an admin. Seeing and transparency (7timer) are displayed in the UI and stats payload but do not contribute to either composite — they inform `seven_timer_tier` instead.

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

### `GET /v1/sky-catalog` — Sky Object Catalog

Returns the static sky object catalog — all objects the engine knows about (planets, named stars, Messier DSOs, meteor showers, ISS). Does not compute visibility; use the Tonight's Sky page or site detail for computed positions.

#### Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `category` | string | ❌ | Filter by category: `planet`, `star`, `dso`, `meteor_shower`, `satellite` |
| `active` | string | ❌ | `true` (default) / `false` / `all` — filter by active flag |

#### Response

```json
{
  "count": 155,
  "objects": [
    {
      "id": 1,
      "name": "M1",
      "common_name": "Crab Nebula",
      "category": "dso",
      "obj_type": "supernova remnant",
      "magnitude": 8.4,
      "ra_h": 5.5755,
      "dec_d": 22.0145,
      "source": "messier_csv",
      "active": true,
      "sort_order": 0,
      "notes": null
    },
    {
      "id": 8,
      "name": "Mercury",
      "category": "planet",
      "obj_type": "planet",
      "magnitude": null,
      "ra_h": null,
      "dec_d": null,
      "source": "de421",
      "active": true,
      "sort_order": 1,
      "ephemeris_name": "mercury"
    },
    {
      "id": 120,
      "name": "Perseids",
      "category": "meteor_shower",
      "obj_type": "meteor_shower",
      "magnitude": null,
      "ra_h": null,
      "dec_d": null,
      "source": "static",
      "active": true,
      "sort_order": 4,
      "peak_month": 8,
      "peak_day": 12,
      "zhr": 100,
      "radiant_ra_h": 3.1,
      "radiant_dec_d": 58.0
    }
  ]
}
```

#### Field notes

| Field | Description |
|---|---|
| `category` | Object category: `planet`, `star`, `dso`, `meteor_shower`, `satellite` |
| `magnitude` | Apparent magnitude. `null` for planets and satellites (computed at runtime) |
| `ra_h` | Right ascension in hours. `null` for planets, ISS, and meteor showers (positions change) |
| `dec_d` | Declination in degrees. `null` for same categories |
| `source` | Data source: `messier_csv`, `yale_bsc`, `de421`, `celestrak`, `static` |
| `ephemeris_name` | *(planet only)* Key used to look up this object in the DE421 ephemeris |
| `peak_month`, `peak_day`, `zhr` | *(meteor_shower only)* Peak date and zenith hourly rate |
| `radiant_ra_h`, `radiant_dec_d` | *(meteor_shower only)* Radiant position in sky |
| `norad_id`, `tle_source_url` | *(satellite only)* NORAD catalog ID and TLE data URL |

#### Error responses

| Status | When |
|---|---|
| `422` | `category` is not a valid value |
| `429` | Rate limit exceeded (60/min) |

---

## Examples

### curl

```bash
# Bortle class lookup
curl "https://starwolf.wolvertons.net/api/v1/bortle?lat=30.67&lon=-104.02"

# Bulk site export
curl "https://starwolf.wolvertons.net/api/v1/sites"

# Basic — 7 days at McDonald Observatory area, Bortle 2
curl "https://starwolf.wolvertons.net/api/v1/forecast?lat=30.67&lon=-104.02&bortle_class=2"

# Longer window in a specific timezone
curl "https://starwolf.wolvertons.net/api/v1/forecast?lat=36.10&lon=-112.11&days=14&timezone=America/Phoenix"

# Sky catalog — all objects
curl "https://starwolf.wolvertons.net/api/v1/sky-catalog"

# Sky catalog — just DSOs
curl "https://starwolf.wolvertons.net/api/v1/sky-catalog?category=dso"

# Sky catalog — all including inactive
curl "https://starwolf.wolvertons.net/api/v1/sky-catalog?active=all"

# Health check
curl "https://starwolf.wolvertons.net/api/healthz"
```

### Python

```python
import requests

resp = requests.get(
    "https://starwolf.wolvertons.net/api/v1/forecast",
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

### Sky catalog

```python
resp = requests.get(
    "https://starwolf.wolvertons.net/api/v1/sky-catalog",
    params={"category": "meteor_shower"},
    timeout=10,
)
resp.raise_for_status()
showers = resp.json()["objects"]

for s in showers:
    print(f"{s['name']:20} peak {s['peak_month']:02d}/{s['peak_day']:02d}  ZHR {s['zhr']}")
```

### Bulk site export

```python
resp = requests.get("https://starwolf.wolvertons.net/api/v1/sites", timeout=10)
resp.raise_for_status()
sites = resp.json()["sites"]

# e.g. filter to IDA-certified dark sky places
ida_sites = [s for s in sites if s["site_type"] == "ida_certified"]
```

### Filter to best nights client-side

```python
good_nights = [n for n in data["nights"] if n["composite"] >= 70]
```

---

## Running the stack

The API is served by the Django container alongside the web app:

```bash
# Start everything
docker compose up -d

# Rebuild after code changes
docker compose build django && docker compose up -d

# Logs
docker compose logs -f django
```
