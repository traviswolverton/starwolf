#!/usr/bin/env python3
"""
Fetch US state parks from OpenStreetMap Overpass API, score each via
the local Bortle API, and write a staging CSV of candidates with
Bortle ≤ 5 that aren't already within 10 km of an existing DB site.

Output: data/staging_state_parks_us.csv

Usage:
    python scripts/fetch_state_parks_us.py
    python scripts/fetch_state_parks_us.py --api http://localhost:8000 --bortle-max 5
"""
import argparse
import csv
import math
import os
import sys
import time

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SITES_API    = "{api}/v1/sites"
BORTLE_API   = "{api}/v1/bortle"
OUTPUT_PATH  = os.path.join(os.path.dirname(__file__), "..", "data", "staging_state_parks_us.csv")

# States already seeded — skip these
ALREADY_SEEDED = {"TX", "MS", "AL", "GA", "FL", "LA"}

# All 50 US states with ISO 3166-2 codes and display names
ALL_STATES = [
    ("AK", "Alaska"),          ("AR", "Arkansas"),        ("AZ", "Arizona"),
    ("CA", "California"),      ("CO", "Colorado"),        ("CT", "Connecticut"),
    ("DE", "Delaware"),        ("HI", "Hawaii"),          ("IA", "Iowa"),
    ("ID", "Idaho"),           ("IL", "Illinois"),        ("IN", "Indiana"),
    ("KS", "Kansas"),          ("KY", "Kentucky"),        ("MA", "Massachusetts"),
    ("MD", "Maryland"),        ("ME", "Maine"),           ("MI", "Michigan"),
    ("MN", "Minnesota"),       ("MO", "Missouri"),        ("MT", "Montana"),
    ("NC", "North Carolina"),  ("ND", "North Dakota"),    ("NE", "Nebraska"),
    ("NH", "New Hampshire"),   ("NJ", "New Jersey"),      ("NM", "New Mexico"),
    ("NV", "Nevada"),          ("NY", "New York"),        ("OH", "Ohio"),
    ("OK", "Oklahoma"),        ("OR", "Oregon"),          ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),    ("SC", "South Carolina"),  ("SD", "South Dakota"),
    ("TN", "Tennessee"),       ("UT", "Utah"),            ("VA", "Virginia"),
    ("VT", "Vermont"),         ("WA", "Washington"),      ("WI", "Wisconsin"),
    ("WV", "West Virginia"),   ("WY", "Wyoming"),
]

OVERPASS_QUERY = """
[out:json][timeout:90];
area["ISO3166-2"="US-{code}"]["boundary"="administrative"]->.state;
(
  relation["boundary"="protected_area"]["protect_class"="5"](area.state);
  relation["boundary"="protected_area"]["ownership"="state"](area.state);
  relation["leisure"="nature_reserve"]["operator"~"[Ss]tate"](area.state);
);
out center tags;
"""

# Name fragments that suggest a site isn't a general-public stargazing venue
_EXCLUDE_KEYWORDS = [
    "wildlife management", "wma", "fish hatchery", "game land",
    "hunting area", "shooting range", "prison", "correctional",
    "military", "air force", "army", "naval",
]


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def fetch_existing_sites(api: str) -> list[tuple[float, float, str]]:
    r = requests.get(SITES_API.format(api=api), timeout=15)
    r.raise_for_status()
    return [(s["lat"], s["lon"], s["name"]) for s in r.json()["sites"]]


def is_too_close(lat, lon, existing, threshold_km=10) -> str | None:
    for slat, slon, sname in existing:
        if _haversine(lat, lon, slat, slon) < threshold_km:
            return sname
    return None


def fetch_parks_for_state(code: str) -> list[dict]:
    query = OVERPASS_QUERY.format(code=code)
    try:
        r = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "StarWolf-App/1.0 (stargazing research)"},
            timeout=120,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"    Overpass error for {code}: {e}")
        return []

    parks = []
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("official_name")
        if not name:
            continue

        # Get center coordinates
        center = el.get("center") or {}
        lat = center.get("lat") or el.get("lat")
        lon = center.get("lon") or el.get("lon")
        if lat is None or lon is None:
            continue

        name_lower = name.lower()
        if any(kw in name_lower for kw in _EXCLUDE_KEYWORDS):
            continue

        parks.append({
            "name":     name,
            "lat":      lat,
            "lon":      lon,
            "operator": tags.get("operator", ""),
            "website":  tags.get("website", ""),
        })

    # Deduplicate by name within the state
    seen = set()
    unique = []
    for p in parks:
        if p["name"] not in seen:
            seen.add(p["name"])
            unique.append(p)
    return unique


def score_bortle(api: str, lat: float, lon: float) -> dict | None:
    try:
        r = requests.get(
            BORTLE_API.format(api=api),
            params={"lat": lat, "lon": lon},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api",        default="http://localhost:8000")
    parser.add_argument("--bortle-max", default=5, type=int)
    parser.add_argument("--output",     default=OUTPUT_PATH)
    args = parser.parse_args()

    print(f"Loading existing sites from {args.api} ...")
    try:
        existing = fetch_existing_sites(args.api)
    except Exception as e:
        sys.exit(f"Cannot reach API at {args.api}: {e}")
    print(f"  {len(existing)} existing sites loaded (proximity threshold: 10 km)\n")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    states_to_query = [(c, n) for c, n in ALL_STATES if c not in ALREADY_SEEDED]
    total_inserted = 0
    total_skipped_bortle = 0
    total_skipped_proximity = 0

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "state_code", "state_name", "name", "lat", "lon",
            "bortle", "sqm", "operator", "proposed_site_type",
        ])
        writer.writeheader()

        for i, (code, state_name) in enumerate(states_to_query, 1):
            print(f"[{i:2d}/{len(states_to_query)}] {state_name} ({code}) ...", end=" ", flush=True)
            parks = fetch_parks_for_state(code)
            print(f"{len(parks)} parks found", end=" ", flush=True)

            state_kept = 0
            for park in parks:
                # Proximity check first (fast)
                dup = is_too_close(park["lat"], park["lon"], existing)
                if dup:
                    total_skipped_proximity += 1
                    continue

                # Bortle score
                result = score_bortle(args.api, park["lat"], park["lon"])
                if result is None:
                    continue

                bortle = result["bortle"]
                if bortle > args.bortle_max:
                    total_skipped_bortle += 1
                    continue

                # Determine site_type
                name_lower = park["name"].lower()
                if "forest" in name_lower:
                    site_type = "national_forest"
                elif "national" in name_lower:
                    site_type = "national_park"
                else:
                    site_type = "state_park"

                writer.writerow({
                    "state_code":        code,
                    "state_name":        state_name,
                    "name":              park["name"],
                    "lat":               round(park["lat"], 5),
                    "lon":               round(park["lon"], 5),
                    "bortle":            bortle,
                    "sqm":               result["sqm"],
                    "operator":          park["operator"],
                    "proposed_site_type": site_type,
                })
                f.flush()

                # Add to existing so subsequent parks in this state get proximity-checked
                existing.append((park["lat"], park["lon"], park["name"]))
                state_kept += 1
                total_inserted += 1

            print(f"→ {state_kept} kept")
            time.sleep(2)  # Overpass rate limit courtesy pause

    print(f"\nDone.")
    print(f"  Staged:            {total_inserted}")
    print(f"  Skipped (Bortle>{args.bortle_max}): {total_skipped_bortle}")
    print(f"  Skipped (too close): {total_skipped_proximity}")
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
