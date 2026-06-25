#!/usr/bin/env python3
"""
Seed expanded Texas stargazing site list.

Tasks performed (all idempotent):
  1. Add site_type column to sites (with CHECK constraint)
  2. Backfill existing rows with site_type='ida_certified'
  3. Create and seed site_types lookup table
  4. Insert new sites — bortle auto-populated, proximity-checked, Permian Basin flagged

Usage:
    DATABASE_URL=postgresql://stargazing:stargazing@localhost:5432/stargazing \
        python seed_expanded_sites.py
"""

import os
import sys

from sqlalchemy import text

from bortle_lookup import lookup_bortle
from db import get_engine
from osm_import import _haversine

_SITE_TYPES = [
    ("ida_certified",   "IDA Certified"),
    ("tx_state_park",   "Texas State Park"),
    ("national_park",   "National Park"),
    ("national_forest", "National Forest"),
    ("observatory",     "Observatory"),
    ("private",         "Private"),
    ("community",       "IDA Dark Sky Community"),
]

# Approximate bounding boxes for Reeves, Pecos, and Culberson counties.
# Sites in these areas with Bortle ≤ 3 get a data-currency caveat because
# the Falchi 2016 GeoTIFF predates significant Permian Basin oilfield growth.
def _is_permian_basin_area(lat: float, lon: float) -> bool:
    return (
        (29.3 <= lat <= 31.5 and -104.5 <= lon <= -100.8) or  # Reeves + Pecos
        (31.0 <= lat <= 32.1 and -105.3 <= lon <= -103.6)      # Culberson
    )

_PERMIAN_CAVEAT = " (2016 data; Permian Basin light growth may affect actual conditions)"

_SITES_TO_SEED = [
    # ── IDA Certified TX State Parks (may already exist; proximity check deduplicates) ──
    {"name": "Big Bend Ranch State Park",         "lat": 29.4000, "lon": -103.7500, "site_type": "ida_certified", "notes": "Bortle 1; darkest skies in Texas; adjacent to Big Bend NP"},
    {"name": "Caprock Canyons State Park",         "lat": 34.4248, "lon": -101.0572, "site_type": "ida_certified", "notes": "IDA Dark Sky Park; Panhandle region"},
    {"name": "Copper Breaks State Park",           "lat": 34.1100, "lon":  -99.7500, "site_type": "ida_certified", "notes": "IDA Dark Sky Park; star parties Apr–Nov"},
    {"name": "Enchanted Rock State Natural Area",  "lat": 30.5063, "lon":  -98.8198, "site_type": "ida_certified", "notes": "IDA Dark Sky Park; Bortle 3; Central TX"},
    {"name": "South Llano River State Park",       "lat": 30.3794, "lon":  -99.8022, "site_type": "ida_certified", "notes": "IDA Dark Sky Park; sells nighttime-only passes"},
    {"name": "Devils River State Natural Area",    "lat": 29.9897, "lon": -100.9761, "site_type": "ida_certified", "notes": "IDA Dark Sky Sanctuary; very remote; plan ahead"},
    {"name": "Black Gap Wildlife Management Area", "lat": 29.4333, "lon": -102.9333, "site_type": "ida_certified", "notes": "IDA Dark Sky Sanctuary; primitive access"},

    # ── TX State Parks — Active Stargazing Programs ───────────────────────────
    {"name": "Davis Mountains State Park",         "lat": 30.5993, "lon": -103.9271, "site_type": "tx_state_park", "notes": "Bortle ~2; near McDonald Observatory; Indian Lodge on-site"},
    {"name": "Balmorhea State Park",               "lat": 30.9450, "lon": -103.7751, "site_type": "tx_state_park", "notes": "Near Davis Mtns; excellent high-desert skies"},
    # Brazos Bend listed before George Observatory — proximity check will skip the observatory
    {"name": "Brazos Bend State Park",             "lat": 29.3731, "lon":  -95.6327, "site_type": "tx_state_park", "notes": "Closest dark site to Houston; Bortle 5–6; George Observatory (Houston Astronomical Society) on-site; alligators"},
    {"name": "Inks Lake State Park",               "lat": 30.7396, "lon":  -98.3699, "site_type": "tx_state_park", "notes": "Hill Country; regular Night Sky Parties"},
    {"name": "Palo Duro Canyon State Park",        "lat": 34.9380, "lon": -101.6771, "site_type": "tx_state_park", "notes": "Largest TX canyon; dark Panhandle skies"},
    {"name": "Garner State Park",                  "lat": 29.5925, "lon":  -99.7472, "site_type": "tx_state_park", "notes": "Hill Country; remote enough for dark skies"},
    {"name": "Lost Maples State Natural Area",     "lat": 29.8122, "lon":  -99.5745, "site_type": "tx_state_park", "notes": "Hill Country; dark and scenic"},
    {"name": "Hill Country State Natural Area",    "lat": 29.6327, "lon":  -99.1821, "site_type": "tx_state_park", "notes": "Near Bandera; known as Cowboy Capital; very dark"},
    {"name": "Resaca de la Palma State Park",      "lat": 26.0641, "lon":  -97.5486, "site_type": "tx_state_park", "notes": "South TX; Dr. Cristina V. Torres Memorial Astronomical Observatory on-site; check events calendar"},
    {"name": "Colorado Bend State Park",           "lat": 31.0224, "lon":  -98.4436, "site_type": "tx_state_park", "notes": "Central TX; remote; Gorman Falls day hike"},
    # Listed in both state parks and national parks tables — load once as national_park
    {"name": "Guadalupe Mountains National Park",  "lat": 31.8926, "lon": -104.8612, "site_type": "national_park", "notes": "West TX; Bortle ~2; one of the least-visited NPs"},

    # ── National Parks ────────────────────────────────────────────────────────
    {"name": "Big Bend National Park",             "lat": 29.1275, "lon": -103.2425, "site_type": "national_park", "notes": "Bortle 1–2; part of Greater Big Bend Dark Sky Reserve; Milky Way casts shadows on moonless nights"},
    # Guadalupe Mountains NP already in list above; proximity check will deduplicate
    {"name": "LBJ National Historical Park",       "lat": 30.2416, "lon":  -98.6268, "site_type": "national_park", "notes": "IDA certified Nov 2021; Hill Country; accessible from Austin/SA"},

    # ── National Forests ──────────────────────────────────────────────────────
    {"name": "Davy Crockett National Forest",      "lat": 31.3871, "lon":  -95.0302, "site_type": "national_forest", "notes": "~2 hrs from Houston; genuinely dark; dispersed camping"},
    {"name": "Sam Houston National Forest",        "lat": 30.7007, "lon":  -95.5172, "site_type": "national_forest", "notes": "Closest forest to Houston; Bortle 4–5; better than the city"},
    {"name": "Angelina National Forest",           "lat": 31.2893, "lon":  -94.1327, "site_type": "national_forest", "notes": "East TX; dark enough for Milky Way on good nights"},
    {"name": "Sabine National Forest",             "lat": 31.4616, "lon":  -93.8002, "site_type": "national_forest", "notes": "East TX; Lake Toledo Bend area; moderate darkness"},

    # ── Observatories / Star Party Venues ─────────────────────────────────────
    {"name": "McDonald Observatory",               "lat": 30.6717, "lon": -104.0225, "site_type": "observatory",     "notes": "Premier public observatory in TX; regular Star Parties; Bortle 1–2"},
    # George Observatory shares coordinates with Brazos Bend SP — will be skipped by proximity
    {"name": "George Observatory",                 "lat": 29.3773, "lon":  -95.6273, "site_type": "observatory",     "notes": "Houston Astronomical Society; inside Brazos Bend SP"},
    {"name": "Canyon of the Eagles Resort",        "lat": 30.7288, "lon":  -98.4408, "site_type": "observatory",     "notes": "Lake Buchanan; Eagle Eye Observatory; Austin Astro Society hosts weekly sessions"},

    # ── IDA Dark Sky Communities ──────────────────────────────────────────────
    {"name": "Dripping Springs",                   "lat": 30.1902, "lon":  -98.0867, "site_type": "community",       "notes": "IDA Dark Sky Community; Hill Country; 30 min from Austin"},
    {"name": "Fredericksburg",                     "lat": 30.2752, "lon":  -98.8719, "site_type": "community",       "notes": "IDA Dark Sky Community; wine country; near Enchanted Rock"},
    {"name": "Fort Davis",                         "lat": 30.5988, "lon": -103.8950, "site_type": "community",       "notes": "IDA Dark Sky Community; anchors the Greater Big Bend Reserve"},
    {"name": "Lakewood Village",                   "lat": 33.1876, "lon":  -96.9463, "site_type": "community",       "notes": "IDA community on Lewisville Lake; dark sky oasis in DFW metro"},
]


def _load_existing(conn) -> list[tuple]:
    return conn.execute(text("SELECT name, lat, lon FROM sites")).fetchall()


def _nearest(lat: float, lon: float, existing: list[tuple]) -> tuple[str, float] | None:
    best_name, best_dist = None, float("inf")
    for name, slat, slon in existing:
        d = _haversine(lat, lon, slat, slon)
        if d < best_dist:
            best_dist, best_name = d, name
    if best_dist < 10:
        return best_name, round(best_dist, 1)
    return None


def main():
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is not set.")

    engine = get_engine()

    # ── 1. Add site_type column ────────────────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'sites' AND column_name = 'site_type'
                ) THEN
                    ALTER TABLE sites ADD COLUMN site_type TEXT CHECK (site_type IN (
                        'ida_certified', 'tx_state_park', 'national_park',
                        'national_forest', 'observatory', 'private', 'community'
                    ));
                END IF;
            END $$;
        """))
    print("site_type column: ready")

    # ── 2. Backfill existing rows ──────────────────────────────────────────────
    with engine.begin() as conn:
        n = conn.execute(text(
            "UPDATE sites SET site_type = 'ida_certified' WHERE site_type IS NULL"
        )).rowcount
    print(f"Backfilled {n} existing rows → site_type='ida_certified'")

    # ── 3. Seed site_types lookup table ───────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS site_types (
                code         TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            )
        """))
        conn.execute(
            text("INSERT INTO site_types (code, display_name) VALUES (:code, :display_name) "
                 "ON CONFLICT (code) DO NOTHING"),
            [{"code": c, "display_name": d} for c, d in _SITE_TYPES],
        )
    print("site_types table: ready")

    # ── 4. Insert new sites ────────────────────────────────────────────────────
    attempted = skipped = inserted = 0
    geotiff_missing_warned = False

    with engine.connect() as conn:
        existing = _load_existing(conn)

    for site in _SITES_TO_SEED:
        attempted += 1
        name = site["name"]

        dup = _nearest(site["lat"], site["lon"], existing)
        if dup:
            print(f"  SKIP   {name:<52} → near {dup[0]!r} ({dup[1]} km)")
            skipped += 1
            continue

        bortle = None
        try:
            bortle = lookup_bortle(site["lat"], site["lon"])["bortle"]
        except FileNotFoundError:
            if not geotiff_missing_warned:
                print("  WARN   GeoTIFF not found — bortle_class will be NULL for all new sites")
                geotiff_missing_warned = True
        except Exception as e:
            print(f"  WARN   Bortle lookup failed for {name!r}: {e}")

        notes = site["notes"]
        if bortle is not None and bortle <= 3 and _is_permian_basin_area(site["lat"], site["lon"]):
            notes += _PERMIAN_CAVEAT

        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO sites "
                     "(name, lat, lon, bortle_class, elevation_m, notes, active, site_type) "
                     "VALUES (:name, :lat, :lon, :bortle, NULL, :notes, 1, :site_type)"),
                {"name": name, "lat": site["lat"], "lon": site["lon"],
                 "bortle": bortle, "notes": notes, "site_type": site["site_type"]},
            )
        existing.append((name, site["lat"], site["lon"]))
        print(f"  INSERT {name:<52} bortle={bortle!s:<4} type={site['site_type']}")
        inserted += 1

    print()
    print(f"Summary: {attempted} attempted, {skipped} skipped, {inserted} inserted")


if __name__ == "__main__":
    main()
