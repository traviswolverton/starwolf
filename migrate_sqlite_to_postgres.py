#!/usr/bin/env python3
"""One-time migration: copy data from stargazing.db (SQLite) into Postgres.

Usage:
    DATABASE_URL=postgresql://stargazing:stargazing@localhost:5432/stargazing \
        python migrate_sqlite_to_postgres.py

Run this AFTER the Docker stack is up and init_db() has created the tables,
but BEFORE switching over to the new stack in production.
"""
import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

SQLITE_PATH = Path(__file__).parent / "stargazing.db"


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL environment variable is not set.")

    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found at {SQLITE_PATH}")

    print(f"Source : {SQLITE_PATH}")
    print(f"Target : {db_url.split('@')[-1]}")  # don't print credentials
    print()

    sqlite_con = sqlite3.connect(SQLITE_PATH)

    # Create tables before migrating data
    os.environ["DATABASE_URL"] = db_url
    from db import init_db
    init_db()
    print("Schema initialised.")

    engine = create_engine(db_url)

    with engine.begin() as conn:
        # ── sites ──────────────────────────────────────────────────────────────
        sites = sqlite_con.execute(
            "SELECT name, lat, lon, bortle_class, elevation_m, notes, active FROM sites"
        ).fetchall()
        if sites:
            conn.execute(text("DELETE FROM sites"))
            conn.execute(
                text("INSERT INTO sites (name, lat, lon, bortle_class, elevation_m, notes, active) "
                     "VALUES (:name, :lat, :lon, :bortle, :elev, :notes, :active)"),
                [{"name": r[0], "lat": r[1], "lon": r[2], "bortle": r[3],
                  "elev": r[4], "notes": r[5], "active": r[6]} for r in sites],
            )
            print(f"  sites            : {len(sites)} rows migrated")

        # ── scoring_weights ────────────────────────────────────────────────────
        weights = sqlite_con.execute(
            "SELECT factor, weight, description FROM scoring_weights"
        ).fetchall()
        if weights:
            conn.execute(text("DELETE FROM scoring_weights"))
            conn.execute(
                text("INSERT INTO scoring_weights (factor, weight, description) "
                     "VALUES (:factor, :weight, :desc)"),
                [{"factor": r[0], "weight": r[1], "desc": r[2]} for r in weights],
            )
            print(f"  scoring_weights  : {len(weights)} rows migrated")

        # ── app_settings ───────────────────────────────────────────────────────
        settings = sqlite_con.execute(
            "SELECT key, value, description FROM app_settings"
        ).fetchall()
        if settings:
            conn.execute(text("DELETE FROM app_settings"))
            conn.execute(
                text("INSERT INTO app_settings (key, value, description) "
                     "VALUES (:key, :value, :desc)"),
                [{"key": r[0], "value": r[1], "desc": r[2]} for r in settings],
            )
            print(f"  app_settings     : {len(settings)} rows migrated")

    sqlite_con.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
