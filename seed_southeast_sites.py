#!/usr/bin/env python3
"""
Seed southeastern US stargazing sites (MS, AL, GA, FL, LA).

- Bortle class auto-populated via GeoTIFF lookup
- Proximity-checked (skips anything within 10 km of an existing site)
- Additive only — no upserts, no overwrites

Usage:
    DATABASE_URL=postgresql://stargazing:stargazing@localhost:5432/stargazing \
        python seed_southeast_sites.py
"""

import os
import sys

from sqlalchemy import text

from bortle_lookup import lookup_bortle
from db import get_engine
from osm_import import _haversine

_SITES_TO_SEED = [
    # ── Mississippi ──────────────────────────────────────────────────────────
    {"name": "Tishomingo State Park",               "lat": 34.6067, "lon": -88.1803, "site_type": "state_park",      "notes": "NE Mississippi; rocky terrain; relatively isolated from urban light"},
    {"name": "De Soto National Forest (Tuxachanie)", "lat": 30.6000, "lon": -89.0500, "site_type": "national_forest", "notes": "Southern MS; Tuxachanie Trail area; limited nearby development"},
    {"name": "Homochitto National Forest",           "lat": 31.4014, "lon": -91.0364, "site_type": "national_forest", "notes": "SW Mississippi; Pipes Lake rec area"},
    {"name": "Wall Doxey State Park",                "lat": 34.7528, "lon": -89.3483, "site_type": "state_park",      "notes": "N Mississippi; spring-fed lake; rural setting"},

    # ── Alabama ───────────────────────────────────────────────────────────────
    {"name": "Cheaha State Park",                    "lat": 33.4858, "lon": -85.8050, "site_type": "state_park",      "notes": "Highest point in Alabama (2,413 ft); elevated horizon aids observing"},
    {"name": "Conecuh National Forest",              "lat": 31.2490, "lon": -86.7947, "site_type": "national_forest", "notes": "S Alabama; longleaf pine restoration area; low population density"},
    {"name": "Bankhead NF / Sipsey Wilderness",      "lat": 34.3000, "lon": -87.3500, "site_type": "national_forest", "notes": "NW Alabama; largest wilderness area east of the Mississippi River"},
    {"name": "DeSoto State Park",                    "lat": 34.4893, "lon": -85.6151, "site_type": "state_park",      "notes": "NE Alabama; atop Lookout Mountain plateau"},
    {"name": "Little River Canyon National Preserve","lat": 34.3706, "lon": -85.6200, "site_type": "national_park",   "notes": "NE Alabama; canyon rim; dark ridge line to the south"},

    # ── Georgia ───────────────────────────────────────────────────────────────
    {"name": "Cloudland Canyon State Park",          "lat": 34.8332, "lon": -85.4832, "site_type": "state_park",      "notes": "NW Georgia; canyon setting reduces horizon light dome"},
    {"name": "Vogel State Park",                     "lat": 34.7640, "lon": -83.9286, "site_type": "state_park",      "notes": "N Georgia mountains; bowl topography provides some shielding"},
    {"name": "Black Rock Mountain State Park",       "lat": 34.9073, "lon": -83.4018, "site_type": "state_park",      "notes": "Highest state park in Georgia (3,640 ft); mountain ridgeline"},
    {"name": "Unicoi State Park",                    "lat": 34.7294, "lon": -83.7165, "site_type": "state_park",      "notes": "NE Georgia mountains near Helen"},
    {"name": "Amicalola Falls State Park",           "lat": 34.5619, "lon": -84.2485, "site_type": "state_park",      "notes": "NW Georgia; approach trail to Appalachian Trail"},
    {"name": "Okefenokee NWR (Stephen Foster SP)",   "lat": 30.7283, "lon": -82.4274, "site_type": "national_park",   "notes": "SE Georgia; extremely low population density; flat terrain"},

    # ── Florida ───────────────────────────────────────────────────────────────
    {"name": "Kissimmee Prairie Preserve State Park","lat": 27.5997, "lon": -81.0506, "site_type": "ida_certified",   "notes": "IDA Dark Sky Park; flattest and darkest open prairie in Florida"},
    {"name": "Jonathan Dickinson State Park",        "lat": 27.0076, "lon": -80.1078, "site_type": "state_park",      "notes": "SE Florida; river swamp; accessible dark-sky option near the Treasure Coast"},
    {"name": "Highlands Hammock State Park",         "lat": 27.4858, "lon": -81.5353, "site_type": "state_park",      "notes": "C Florida; old-growth hammock; some buffer from I-4 corridor"},
    {"name": "Lake Kissimmee State Park",            "lat": 27.9581, "lon": -81.3862, "site_type": "state_park",      "notes": "C Florida; open prairie and marsh; away from major urban cores"},
    {"name": "Ocala National Forest",                "lat": 29.2000, "lon": -81.8000, "site_type": "national_forest", "notes": "C Florida; largest contiguous forest block in the state"},
    {"name": "Apalachicola National Forest (Camel Lake)","lat": 30.1000, "lon": -84.8000, "site_type": "national_forest", "notes": "NW Florida panhandle; remote primitive camping area; very dark"},
    {"name": "Fakahatchee Strand Preserve State Park","lat": 25.9736, "lon": -81.3681, "site_type": "state_park",     "notes": "SW Florida; remote swamp; minimal development nearby"},
    {"name": "Everglades National Park (Flamingo)",  "lat": 25.1378, "lon": -80.9256, "site_type": "national_park",   "notes": "Southernmost point; no light to the south; remote and very dark"},
    {"name": "Big Cypress National Preserve",        "lat": 26.0000, "lon": -81.0000, "site_type": "national_park",   "notes": "SW Florida; vast wilderness; dark but humidity can affect transparency"},

    # ── Louisiana ─────────────────────────────────────────────────────────────
    {"name": "Kisatchie National Forest",            "lat": 31.3000, "lon": -92.5000, "site_type": "national_forest", "notes": "C Louisiana; largest national forest in the state; Wild Azalea Trail area"},
    {"name": "Chicot State Park",                    "lat": 30.7833, "lon": -92.2833, "site_type": "state_park",      "notes": "SC Louisiana; around Lake Chicot; rural setting"},
    {"name": "Hodges Gardens State Park",            "lat": 31.2350, "lon": -93.2750, "site_type": "state_park",      "notes": "W Louisiana; 4,700-acre garden and wilderness; remote"},
    {"name": "Lake Bistineau State Park",            "lat": 32.5333, "lon": -93.3667, "site_type": "state_park",      "notes": "NW Louisiana; cypress-tupelo swamp; low population density"},
    {"name": "Poverty Point Reservoir State Park",   "lat": 32.6340, "lon": -91.4030, "site_type": "state_park",      "notes": "NE Louisiana; flatlands; well isolated from major cities"},
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

    # Ensure state_park is in the site_types lookup table
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO site_types (code, display_name) VALUES ('state_park', 'State Park') "
            "ON CONFLICT (code) DO NOTHING"
        ))

    attempted = skipped = inserted = 0

    with engine.connect() as conn:
        existing = _load_existing(conn)

    for site in _SITES_TO_SEED:
        attempted += 1
        name = site["name"]

        dup = _nearest(site["lat"], site["lon"], existing)
        if dup:
            print(f"  SKIP   {name:<55} → near {dup[0]!r} ({dup[1]} km)")
            skipped += 1
            continue

        bortle = None
        try:
            bortle = lookup_bortle(site["lat"], site["lon"])["bortle"]
        except FileNotFoundError:
            print("  WARN   GeoTIFF not found — bortle_class will be NULL")
        except Exception as e:
            print(f"  WARN   Bortle lookup failed for {name!r}: {e}")

        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO sites "
                     "(name, lat, lon, bortle_class, elevation_m, notes, active, site_type) "
                     "VALUES (:name, :lat, :lon, :bortle, NULL, :notes, 1, :site_type)"),
                {"name": name, "lat": site["lat"], "lon": site["lon"],
                 "bortle": bortle, "notes": site["notes"], "site_type": site["site_type"]},
            )
        existing.append((name, site["lat"], site["lon"]))
        print(f"  INSERT {name:<55} bortle={bortle!s:<4} type={site['site_type']}")
        inserted += 1

    print()
    print(f"Summary: {attempted} attempted, {skipped} skipped, {inserted} inserted")


if __name__ == "__main__":
    main()
