# Sky Object Catalog — Unified Data Model

**Status:** Implemented  
**Shipped:** 2026-06-28

---

## Goal

Replace the current ad-hoc per-category dicts (hardcoded planet list, Messier CSV, hardcoded showers, ISS) with a single DB-backed catalog table. The catalog is the registry of *what to show* — the engine computes *where and when* at runtime based on category.

---

## DB Table: `sky_catalog`

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `name` | text | Jupiter, M31, Sirius, Perseids, ISS… |
| `common_name` | text | nullable — Andromeda Galaxy, Dog Star… |
| `category` | enum | drives engine branch (see below) |
| `obj_type` | text | galaxy, globular, open cluster, nebula, planet, star, meteor shower, satellite |
| `magnitude` | float | null → computed at runtime |
| `ra_h` | float | null → computed at runtime (planets, ISS, showers) |
| `dec_d` | float | null → computed at runtime |
| `source` | text | messier_csv, yale_bsc, de421, celestrak, static |
| `active` | bool | toggle without deleting |
| `sort_order` | int | display ordering within category |
| `notes` | text | nullable |
| `extra_data` | jsonb | category-specific fields (see below) |

### Category-Specific `extra_data`

| Category | Fields |
|---|---|
| `planet` | `{"ephemeris_name": "mars"}` — name used for DE421 lookup |
| `satellite` | `{"norad_id": 25544, "tle_source_url": "https://celestrak.org/..."}` |
| `meteor_shower` | `{"peak_month": 8, "peak_day": 12, "zhr": 100, "radiant_ra_h": 3.0, "radiant_dec_d": 58.0}` |
| `star` | `{}` — RA/Dec in main columns, no extras needed |
| `dso` | `{}` — RA/Dec in main columns, no extras needed |

---

## Categories & Row Counts

| Category | Rows | Position Source |
|---|---|---|
| `planet` | 7 | DE421 ephemeris (skyfield) |
| `star` | ~25 | Fixed RA/Dec — Yale Bright Star Catalog |
| `dso` | 110+ | Fixed RA/Dec — Messier CSV (NGC/IC future) |
| `meteor_shower` | ~12 | Radiant RA/Dec + peak date in `extra_data` |
| `satellite` | 1+ | Celestrak TLE (live fetch, cached 6h) |

---

## Computed Output (per request, not stored)

All computed at runtime by `sky_objects.py` based on observer lat/lon, date, and Bortle class:

| Field | Notes |
|---|---|
| `rise_str` / `peak_str` / `set_str` | Formatted local time strings |
| `peak_alt` | Degrees above horizon at peak |
| `peak_az` | Compass direction at peak (16-point) |
| `vis_start` / `vis_end` | When above 10° during the night window |
| `tier` / `tier_label` / `tier_emoji` | Visibility tier based on mag + Bortle |
| `visible` | Bool — above horizon and within limiting mag |
| `magnitude` | Echoed from catalog, or computed for planets |
| `duration_m` | Satellites only — pass duration in minutes |

---

## Data Loaders

Management command: `seed_sky_catalog` (idempotent — safe to re-run)

| Source | Rows seeded |
|---|---|
| `engine/data/messier.csv` | 110 DSO rows |
| `engine/data/stars.csv` *(new)* | ~25 star rows — Yale BSC, mag < 2.0 |
| Hardcoded | 7 planets + 12 annual meteor showers + ISS |

---

## Public API

```
GET /v1/sky-catalog
```

Returns the static catalog (not computed positions). Filterable:

| Param | Example | Description |
|---|---|---|
| `category` | `dso` | Filter by category |
| `active` | `true` | Filter by active flag (default: true) |

Returns catalog rows only — use `GET /sites/<id>/sky` or `GET /tonight` for computed visibility.

---

## Engine Refactor (`sky_objects.py`)

Instead of hardcoded lists, `compute_sky()` queries the catalog and branches on `category`:

```python
objects = SkyObject.objects.filter(active=True).order_by('category', 'sort_order')
for obj in objects:
    if obj.category == 'planet':
        # use DE421 + obj.extra_data['ephemeris_name']
    elif obj.category in ('star', 'dso'):
        # use fixed RA/Dec
    elif obj.category == 'meteor_shower':
        # use extra_data peak date + radiant coords
    elif obj.category == 'satellite':
        # fetch TLE from Celestrak using extra_data['norad_id']
```

---

## Build Order

1. Django model + migration (`SkyObject` table)
2. `seed_sky_catalog` management command (CSV + hardcoded data)
3. `engine/data/stars.csv` — curated bright star list
4. Refactor `sky_objects.py` to query catalog instead of hardcoded lists
5. Admin panel list view (toggle active, sort_order)
6. `GET /v1/sky-catalog` API endpoint + docs
