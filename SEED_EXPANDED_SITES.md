# StarWolf: Expanded Site Seed + `site_type` Migration

## Context

StarWolf has a PostgreSQL `sites` table with existing IDA-certified dark sky sites already loaded. Those sites have `bortle_class` values populated via the existing Bortle GeoTIFF lookup utility. We are now expanding the seed list to include Texas state parks, national parks, national forests, observatories, and other notable stargazing sites across Texas.

---

## Task 1: Add `site_type` Column

Add a `site_type TEXT` column to the `sites` table. Use a controlled vocabulary — do not allow arbitrary values. Apply a `CHECK` constraint:

```sql
ALTER TABLE sites
  ADD COLUMN site_type TEXT
  CHECK (site_type IN (
    'ida_certified',
    'tx_state_park',
    'national_park',
    'national_forest',
    'observatory',
    'private',
    'community'
  ));
```

Then backfill all existing rows (which are IDA-certified sites) with `site_type = 'ida_certified'`.

---

## Task 2: Seed Expanded Site List

Write a seed script (e.g. `seed_expanded_sites.py`) that loads the following sites using the **same pattern used to load the IDA sites** — including:

- Bortle class auto-populated via the existing GeoTIFF lookup utility
- Elevation populated if available via existing logic (or left NULL if not)
- Duplicate detection using the existing proximity check (skip any site that is already too close to an existing site in the DB)
- `active = 1` for all new rows
- Additive only — do not upsert, do not overwrite existing rows

The `notes` field should be populated per site where there is something useful to say (e.g. Permian Basin Bortle caveat, observatory on-site, overnight access requirements).

---

## Sites to Seed

### Texas State Parks — IDA Certified (may already exist; proximity check will catch duplicates)

| Name | Lat | Lon | site_type | Notes |
|------|-----|-----|-----------|-------|
| Big Bend Ranch State Park | 29.4000 | -103.7500 | ida_certified | Bortle 1; darkest skies in Texas; adjacent to Big Bend NP |
| Caprock Canyons State Park | 34.4248 | -101.0572 | ida_certified | IDA Dark Sky Park; Panhandle region |
| Copper Breaks State Park | 34.1100 | -99.7500 | ida_certified | IDA Dark Sky Park; star parties Apr–Nov |
| Enchanted Rock State Natural Area | 30.5063 | -98.8198 | ida_certified | IDA Dark Sky Park; Bortle 3; Central TX |
| South Llano River State Park | 30.3794 | -99.8022 | ida_certified | IDA Dark Sky Park; sells nighttime-only passes |
| Devils River State Natural Area | 29.9897 | -100.9761 | ida_certified | IDA Dark Sky Sanctuary; very remote; plan ahead |
| Black Gap Wildlife Management Area | 29.4333 | -102.9333 | ida_certified | IDA Dark Sky Sanctuary; primitive access |

### Texas State Parks — Active Stargazing Programs / Notable Dark Skies

| Name | Lat | Lon | site_type | Notes |
|------|-----|-----|-----------|-------|
| Davis Mountains State Park | 30.5993 | -103.9271 | tx_state_park | Bortle ~2; near McDonald Observatory; Indian Lodge on-site |
| Balmorhea State Park | 30.9450 | -103.7751 | tx_state_park | Near Davis Mtns; excellent high-desert skies |
| Brazos Bend State Park | 29.3731 | -95.6327 | tx_state_park | Closest dark site to Houston; Bortle 5–6; alligators |
| Inks Lake State Park | 30.7396 | -98.3699 | tx_state_park | Hill Country; regular Night Sky Parties |
| Palo Duro Canyon State Park | 34.9380 | -101.6771 | tx_state_park | Largest TX canyon; dark Panhandle skies |
| Garner State Park | 29.5925 | -99.7472 | tx_state_park | Hill Country; remote enough for dark skies |
| Lost Maples State Natural Area | 29.8122 | -99.5745 | tx_state_park | Hill Country; dark and scenic |
| Hill Country State Natural Area | 29.6327 | -99.1821 | tx_state_park | Near Bandera; known as Cowboy Capital; very dark |
| Resaca de la Palma State Park | 26.0641 | -97.5486 | tx_state_park | South TX; has on-site Dr. Cristina V. Torres Memorial Astronomical Observatory; check events calendar |
| Colorado Bend State Park | 31.0224 | -98.4436 | tx_state_park | Central TX; remote; Gorman Falls day hike |
| Guadalupe Mountains National Park (Pine Springs) | 31.8926 | -104.8612 | national_park | Use national_park type; remote West TX; Bortle ~2 |

### National Parks

| Name | Lat | Lon | site_type | Notes |
|------|-----|-----|-----------|-------|
| Big Bend National Park | 29.1275 | -103.2425 | national_park | Bortle 1–2; part of Greater Big Bend Dark Sky Reserve; Milky Way casts shadows on moonless nights |
| Guadalupe Mountains National Park | 31.8926 | -104.8612 | national_park | West TX; Bortle ~2; one of the least-visited NPs |
| LBJ National Historical Park | 30.2416 | -98.6268 | national_park | IDA certified Nov 2021; Hill Country; accessible from Austin/SA |

### National Forests

| Name | Lat | Lon | site_type | Notes |
|------|-----|-----|-----------|-------|
| Davy Crockett National Forest | 31.3871 | -95.0302 | national_forest | ~2 hrs from Houston; genuinely dark; dispersed camping |
| Sam Houston National Forest | 30.7007 | -95.5172 | national_forest | Closest forest to Houston; Bortle 4–5; better than the city |
| Angelina National Forest | 31.2893 | -94.1327 | national_forest | East TX; dark enough for Milky Way on good nights |
| Sabine National Forest | 31.4616 | -93.8002 | national_forest | East TX; Lake Toledo Bend area; moderate darkness |

### Public Observatories / Star Party Venues

| Name | Lat | Lon | site_type | Notes |
|------|-----|-----|-----------|-------|
| McDonald Observatory | 30.6717 | -104.0225 | observatory | Premier public observatory in TX; regular Star Parties; Bortle 1–2 |
| George Observatory (Brazos Bend) | 29.3773 | -95.6273 | observatory | Houston Astronomical Society; inside Brazos Bend SP |
| Canyon of the Eagles Resort | 30.7288 | -98.4408 | observatory | Lake Buchanan; Eagle Eye Observatory; Austin Astro Society hosts weekly sessions |

### IDA Dark Sky Communities

| Name | Lat | Lon | site_type | Notes |
|------|-----|-----|-----------|-------|
| Dripping Springs | 30.1902 | -98.0867 | community | IDA Dark Sky Community; Hill Country; 30 min from Austin |
| Fredericksburg | 30.2752 | -98.8719 | community | IDA Dark Sky Community; wine country; near Enchanted Rock |
| Fort Davis | 30.5988 | -103.8950 | community | IDA Dark Sky Community; anchors the Greater Big Bend Reserve |
| Lakewood Village | 33.1876 | -96.9463 | community | IDA community on Lewisville Lake; dark sky oasis in DFW metro |

---

## Important Notes for Claude Code

- **Permian Basin caveat**: Sites in or near the Permian Basin (Pecos County, Reeves County, Culberson County areas) may return optimistic Bortle values from the 2016 Falchi GeoTIFF due to significant oilfield light pollution growth since that dataset was published. Flag these in the notes field if Bortle lookup returns ≤3 for sites in that region — consider adding "(2016 data; Permian Basin light growth may affect actual conditions)" to notes.
- **Guadalupe Mountains** appears twice in the seed list above (once in the State Parks table with a note to use `national_park` type, once in National Parks). The proximity check should deduplicate — but if not, load it once as `national_park`.
- **George Observatory** shares coordinates with Brazos Bend SP — proximity check may flag this. If so, load only the state park entry and add a note about the observatory being on-site.
- Do **not** insert any site that already exists or is within the proximity threshold of an existing site.
- Print a summary at the end: sites attempted, sites skipped (duplicate/proximity), sites inserted.
