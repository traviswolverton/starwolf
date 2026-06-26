#!/usr/bin/env python3
"""
Seed all staged US state parks from data/staging_state_parks_us.csv.

The CSV was already proximity-checked and Bortle-filtered when generated.
This script does a final proximity check against the live DB before inserting
in case the DB changed since the CSV was produced.

Usage:
    DATABASE_URL=postgresql://stargazing:stargazing@localhost:5432/stargazing \
        python seed_us_state_parks.py
"""

import csv
import os
import sys

from sqlalchemy import text

from db import get_engine
from osm_import import _haversine

CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "staging_state_parks_us.csv")


def main():
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is not set.")

    engine = get_engine()

    with engine.connect() as conn:
        existing = conn.execute(text("SELECT name, lat, lon FROM sites")).fetchall()
        existing = [(r.lat, r.lon, r.name) for r in existing]

    print(f"Loaded {len(existing)} existing sites.")

    with open(CSV_PATH, newline="") as f:
        rows = list(csv.DictReader(f))

    print(f"CSV contains {len(rows)} candidates.\n")

    attempted = skipped = inserted = 0

    for row in rows:
        attempted += 1
        lat  = float(row["lat"])
        lon  = float(row["lon"])
        name = row["name"]

        # Final proximity check against current DB
        too_close = next(
            (sname for slat, slon, sname in existing
             if _haversine(lat, lon, slat, slon) < 10),
            None,
        )
        if too_close:
            skipped += 1
            continue

        bortle    = int(row["bortle"]) if row["bortle"] else None
        site_type = row["proposed_site_type"]

        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO sites "
                     "(name, lat, lon, bortle_class, elevation_m, notes, active, site_type) "
                     "VALUES (:name, :lat, :lon, :bortle, NULL, :notes, 1, :site_type)"),
                {
                    "name":      name,
                    "lat":       lat,
                    "lon":       lon,
                    "bortle":    bortle,
                    "notes":     f"{row['state_name']} — {row['operator']}".strip(" —"),
                    "site_type": site_type,
                },
            )

        existing.append((lat, lon, name))
        inserted += 1
        if inserted % 100 == 0:
            print(f"  {inserted} inserted so far...")

    print(f"\nDone. {attempted} attempted, {inserted} inserted, {skipped} skipped (proximity).")


if __name__ == "__main__":
    main()
