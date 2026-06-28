# "What Would I See?" — Feature Spec

**Status:** ✅ Implemented 2026-06-27 (Spec 1 + Spec 2 shipped together)  
**Preceded by:** Site Detail pages (`site_details` table, `enrich_site_details` management command)  
**Depends on:** `skyfield`, Messier catalog CSV, existing Bortle lookup pipeline  
**Session context:** Scoped 2026-06-27 while `enrich_site_details` full-catalog run was in progress

---

## Background

StarWolf currently answers **"when is the best date/site?"** via the Planner and heatmap.  
This feature answers **"what would I actually see?"** — making the forecast actionable by telling
the user which celestial objects are visible on a given night, from a given location, and how
realistically they can expect to see them given light pollution and (optionally) weather.

---

## Core Model: Visibility Likelihood

Every observable object has a **magnitude** (brightness — lower number = brighter).  
Every site has a **limiting magnitude** derived from its Bortle class — the faintest object
a naked eye can detect under those conditions.

### Bortle → Limiting Magnitude

| Bortle | Naked Eye Limit |
|--------|----------------|
| 1 | 7.6 mag |
| 2 | 7.1 mag |
| 3 | 6.6 mag |
| 4 | 6.1 mag |
| 5 | 5.6 mag |
| 6 | 5.1 mag |
| 7 | 4.5 mag |
| 8 | 4.0 mag |
| 9 | 3.0 mag |

### Equipment Tiers (magnitude gain over naked eye)

| Equipment | Gain | Notes |
|-----------|------|-------|
| Naked eye | +0 | |
| Binoculars (7×50) | +3 | |
| Small telescope (4") | +5 | |
| Large telescope (10"+) | +7 | |

### Visibility Tier

Compare object's required magnitude against `site_limiting_mag + equipment_gain`.

| Tier | Emoji | Label | Meaning |
|------|-------|-------|---------|
| 0 | 🟢 | **Naked Eye** | Visible without equipment |
| 1 | 🔵 | **Binoculars** | Visible with standard binoculars |
| 2 | 🔭 | **Small Scope** | 4–6" telescope needed |
| 3 | 🔭🔭 | **Large Scope** | 10"+ telescope, dark sky required |
| 4 | ⛔ | **Not Tonight** | Below threshold even with large scope, or below horizon |

**Altitude penalty:** Objects below ~15° elevation suffer atmospheric extinction (~1–2 mag loss).
`skyfield` provides exact altitude/azimuth for any lat/lon/datetime — apply extinction before
computing the visibility tier.

**Weather modifier (Spec 1 only):** When forecast data is available, multiply tier confidence
by the cloud cover score from the existing pipeline. Add a banner to the UI if conditions
are poor.

---

## Object Catalog

All data is bundled locally — no external API required at runtime.

| Category | Source | Count | Notes |
|----------|--------|-------|-------|
| Planets | `skyfield` DE421 ephemeris | 7 (Mercury–Neptune) | Ephemeris file ~17MB, bundle in container |
| Moon | `astral` (already in use) | 1 | Phase + rise/set already computed elsewhere |
| Messier DSOs | Bundled CSV | 110 | See schema below |
| Bright named stars | Curated list (mag < 2.5) | ~30 | Vega, Arcturus, Sirius, etc. |
| ISS passes | Celestrak TLE (cached 6h) | on demand | `https://celestrak.org/SOCRATES/` |
| Meteor showers | Static annual calendar | ~12 active events | ZHR, radiant, peak dates |

### Messier Catalog CSV Schema

```
name, type, ra_h, ra_m, ra_s, dec_d, dec_m, dec_s, magnitude, size_arcmin, common_name, notes
M1, Nebula, 5, 34, 32, +22, 0, 52, 8.4, 7, Crab Nebula, Supernova remnant
M13, Globular, 16, 41, 41, +36, 27, 41, 5.8, 20, Hercules Cluster, Best globular in northern sky
M31, Galaxy, 0, 42, 44, +41, 16, 9, 3.4, 178, Andromeda Galaxy, Naked eye from dark sites
...
```

---

## Spec 1 — "What Might I See?" on Site Detail Page

### Context

User is on a site detail page (e.g., McDonald Observatory, Big Bend).  
Site has known lat/lon and Bortle class. A new "What's Up" section appears below the narrative.

### Inputs

- Site lat/lon + Bortle class (already in context)
- Date picker (default: tonight in site's local timezone)
- Forecast cloud cover score (optional — pulled from Redis cache if already computed)

### Output Format

Grouped by category, sorted by visibility tier within each group.  
Night window = astronomical twilight end → astronomical twilight start.

```
🌙 Moon — Waxing Gibbous (68% illuminated)
   Rises 3:14p · Sets 1:42a · Peak altitude 61° at 9:28p
   ⚠️ Bright moon may wash out faint DSOs tonight

🪐 Planets visible tonight
   Jupiter    🟢 Naked Eye   mag -2.4   Rises 8:47p · Peak 52° at 1:12a
   Saturn     🟢 Naked Eye   mag +0.7   Rises 7:30p · Peak 38° at 11:45p
   Mars       🔵 Binoculars  mag +1.6   Rises 11:14p · Sets 6:02a
   Venus      ⛔ Below horizon until Aug

🌌 Deep Sky Objects (top picks for tonight)
   M13  Hercules Cluster    🟢 Naked Eye   Globular  mag 5.8   Visible 9p–2a  Peak 71°
   M57  Ring Nebula         🔭 Small Scope Nebula    mag 8.8   Visible 10p–3a Peak 58°
   M31  Andromeda Galaxy    🔵 Binoculars  Galaxy    mag 3.4   Rises 11p      Peak 42°

☄️ Meteor Showers
   Perseids — Peak Aug 11–12 (3 days away) · ~100/hr ZHR · Radiant rises at midnight

🛸 ISS Passes
   Tonight 9:14p · Duration 6 min · Max elevation 72° · SW → NE
```

### Weather Integration

When cloud cover forecast is available for this site/night:
- Good conditions (cloud score ≥ 70): *"Clear skies expected — excellent conditions for the above."*
- Marginal (40–69): *"Partly cloudy forecast — some objects may be obscured. Check the Planner for a clearer night."*
- Poor (< 40): *"Significant cloud cover expected. Visibility tiers assume clear skies."*

### Implementation Notes

- Add `skyfield` and DE421 ephemeris to `requirements.txt` and `Dockerfile.django`
- Create `django/engine/sky_objects.py` — computes visibility for a lat/lon/date
- Create `django/engine/messier.py` — loads and filters the bundled catalog CSV
- New Django view: `sky_objects(request, site_id)` — HTMX target, accepts `?date=YYYY-MM-DD`
- Cache key: `sky:{site_id}:{date}` → 1 hour TTL in Redis
- Template: new `_sky_objects.html` partial, loaded via HTMX on page load / date change
- Date picker in template triggers `hx-get` on change (no page reload)

---

## Spec 2 — "What's in the Sky Tonight?" — Location-Based, No Forecast Required

### Context

Standalone feature accessible before any planning. User provides only a location.  
No site from the catalog required. No forecast run required.

**Key difference from Spec 1:** Bortle class is derived on the fly from the World Atlas GeoTIFF
via the existing `lookup_bortle(lat, lon)` function. No weather data — likelihood is purely
astronomical + light pollution.

### Entry Points

1. **Homepage widget:** "What's up tonight near you?" → uses saved prefs location if logged in,
   otherwise prompts for city/zip (reuse address autocomplete from Set Location page)
2. **New nav/page:** "Tonight's Sky" — distinct from the existing heatmap page
3. **Planner setup card:** Quick sky summary for the user's home location before running a full forecast

### Output

Same format as Spec 1 with two additions:

**Bortle source note:** *(Light pollution: Bortle 5 — suburban skies near your location)*

**"Drive to a dark site" nudge** — after the object list, show objects that are above the horizon
*tonight* but too faint to see from the user's location due to light pollution:

```
🚗 Worth the drive tonight
   These objects are above the horizon but washed out from your location (Bortle 5).
   Head to a dark site (Bortle ≤ 3) to unlock:
   M1  Crab Nebula      needs Bortle ≤ 4   Currently at 34° altitude — visible until 2a
   M97 Owl Nebula       needs Bortle ≤ 3   Currently at 29° altitude — visible until 1a
   → Find a dark site nearby [links to Planner]
```

This creates a direct funnel from curiosity → Planner → site visit.

### Implementation Notes

- Reuses `django/engine/sky_objects.py` from Spec 1 (same computation, different Bortle source)
- New view: `tonight(request)` — renders the page for the user's saved location
- HTMX location input → updates results without page reload
- Guest-accessible (no login required) — use `_GuestPrefs` lat/lon as default if no saved location

---

## Build Order

1. Add `skyfield` + DE421 to container; create `sky_objects.py` + `messier.py`
2. **Spec 1, planets + moon only** — high value, fast to implement, validates the skyfield integration
3. **Spec 1, Messier catalog** — bundle CSV, filter by altitude + visibility tier
4. **Spec 1, ISS passes** — one Celestrak fetch, fun and easy
5. **Spec 1, weather integration** — soft dependency, reuses existing forecast cache
6. **Spec 2** — mostly reuses Spec 1 engine; add Bortle on-the-fly lookup + "drive to dark site" nudge

---

## Open Questions

- Should DSOs be limited to Messier only, or include NGC/IC? (Messier is a good v1 scope — 110 well-known objects)
- Show constellations? (Cosmetic, could be done with a static polygon dataset)
- Astrophotography mode? (Different equipment model — sensor sensitivity instead of eye limiting mag)
- User equipment preference (binoculars vs. small scope vs. large scope) stored in Prefs?
  This would make the visibility tier personal rather than showing all tiers at once.
