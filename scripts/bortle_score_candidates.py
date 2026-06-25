#!/usr/bin/env python3
"""
Score candidate sites from southeast_sites_staging.md against the Bortle API.
Prints a markdown table sorted by Bortle class (darkest first).

Usage:
    python scripts/bortle_score_candidates.py
    python scripts/bortle_score_candidates.py --api http://localhost:8000
"""
import argparse
import sys
import requests

API_DEFAULT = "http://localhost:8000"

CANDIDATES = [
    ("Tishomingo State Park",                    "MS", 34.6067, -88.1803, "state_park"),
    ("De Soto NF (Tuxachanie Trail)",            "MS", 30.6000, -89.0500, "national_forest"),
    ("Homochitto NF (Pipes Lake)",               "MS", 31.4014, -91.0364, "national_forest"),
    ("Wall Doxey State Park",                    "MS", 34.7528, -89.3483, "state_park"),
    ("Cheaha State Park",                        "AL", 33.4858, -85.8050, "state_park"),
    ("Conecuh National Forest",                  "AL", 31.2490, -86.7947, "national_forest"),
    ("Bankhead NF / Sipsey Wilderness",          "AL", 34.3000, -87.3500, "national_forest"),
    ("DeSoto State Park",                        "AL", 34.4893, -85.6151, "state_park"),
    ("Little River Canyon National Preserve",    "AL", 34.3706, -85.6151, "national_park"),
    ("Cloudland Canyon State Park",              "GA", 34.8332, -85.4832, "state_park"),
    ("Vogel State Park",                         "GA", 34.7640, -83.9286, "state_park"),
    ("Black Rock Mountain State Park",           "GA", 34.9073, -83.4018, "state_park"),
    ("Unicoi State Park",                        "GA", 34.7294, -83.7165, "state_park"),
    ("Amicalola Falls State Park",               "GA", 34.5619, -84.2485, "state_park"),
    ("Okefenokee NWR (Stephen Foster SP)",       "GA", 30.7283, -82.4274, "national_park"),
    ("Kissimmee Prairie Preserve SP",            "FL", 27.5997, -81.0506, "ida_certified"),
    ("Jonathan Dickinson State Park",            "FL", 27.0076, -80.1078, "state_park"),
    ("Highlands Hammock State Park",             "FL", 27.4858, -81.5353, "state_park"),
    ("Lake Kissimmee State Park",                "FL", 27.9581, -81.3862, "state_park"),
    ("Ocala NF (Lake Oklawaha)",                 "FL", 29.2000, -81.8000, "national_forest"),
    ("Apalachicola NF (Camel Lake)",             "FL", 30.1000, -84.8000, "national_forest"),
    ("Fakahatchee Strand Preserve SP",           "FL", 25.9736, -81.3681, "state_park"),
    ("Everglades NP (Flamingo)",                 "FL", 25.1378, -80.9256, "national_park"),
    ("Big Cypress National Preserve",            "FL", 26.0000, -81.0000, "national_park"),
    ("Kisatchie NF (Wild Azalea area)",          "LA", 31.3000, -92.5000, "national_forest"),
    ("Chicot State Park",                        "LA", 30.7833, -92.2833, "state_park"),
    ("Hodges Gardens State Park",                "LA", 31.2350, -93.2750, "state_park"),
    ("Lake Bistineau State Park",                "LA", 32.5333, -93.3667, "state_park"),
    ("Poverty Point Reservoir SP",               "LA", 32.6340, -91.4030, "state_park"),
]


def score(api_base: str, name: str, lat: float, lon: float) -> dict:
    try:
        r = requests.get(f"{api_base}/v1/bortle", params={"lat": lat, "lon": lon}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API_DEFAULT, help="API base URL")
    args = parser.parse_args()

    print(f"Querying {args.api} ...\n")

    results = []
    for name, state, lat, lon, site_type in CANDIDATES:
        data = score(args.api, name, lat, lon)
        bortle = data.get("bortle", "ERR")
        sqm    = data.get("sqm",    "ERR")
        error  = data.get("error", "")
        results.append((bortle if isinstance(bortle, int) else 99, name, state, lat, lon, bortle, sqm, site_type, error))
        marker = f"Bortle {bortle}, SQM {sqm}" if not error else f"ERROR: {error}"
        print(f"  {state}  {name:<45} {marker}")

    results.sort()

    print("\n\n## Results — sorted by Bortle class (darkest first)\n")
    print(f"{'Bortle':<8} {'SQM':<7} {'State':<6} {'site_type':<16} {'Name'}")
    print("-" * 80)
    for _, name, state, lat, lon, bortle, sqm, site_type, error in results:
        if error:
            print(f"{'ERR':<8} {'ERR':<7} {state:<6} {site_type:<16} {name}  !! {error}")
        else:
            print(f"{bortle:<8} {sqm:<7} {state:<6} {site_type:<16} {name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
