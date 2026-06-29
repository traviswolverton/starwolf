"""
Management command: seed_sky_catalog
Populates the sky_catalog table from bundled CSVs and hardcoded data.
Idempotent — safe to re-run; uses upsert on (name, category).

Usage:
  python manage.py seed_sky_catalog            # seed all categories
  python manage.py seed_sky_catalog --clear    # wipe and re-seed
"""
import csv
import os

from django.core.management.base import BaseCommand

from accounts.models import SkyObject

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "engine", "data")


PLANETS = [
    {"name": "Mercury", "obj_type": "planet", "sort_order": 1, "extra_data": {"ephemeris_name": "mercury"}},
    {"name": "Venus",   "obj_type": "planet", "sort_order": 2, "extra_data": {"ephemeris_name": "venus"}},
    {"name": "Mars",    "obj_type": "planet", "sort_order": 3, "extra_data": {"ephemeris_name": "mars"}},
    {"name": "Jupiter", "obj_type": "planet", "sort_order": 4, "extra_data": {"ephemeris_name": "jupiter barycenter"}},
    {"name": "Saturn",  "obj_type": "planet", "sort_order": 5, "extra_data": {"ephemeris_name": "saturn barycenter"}},
    {"name": "Uranus",  "obj_type": "planet", "sort_order": 6, "extra_data": {"ephemeris_name": "uranus barycenter"}},
    {"name": "Neptune", "obj_type": "planet", "sort_order": 7, "extra_data": {"ephemeris_name": "neptune barycenter"}},
]

METEOR_SHOWERS = [
    {"name": "Quadrantids",   "extra_data": {"peak_month": 1,  "peak_day": 3,  "zhr": 120, "radiant_ra_h": 15.3, "radiant_dec_d": 49.5}},
    {"name": "Lyrids",        "extra_data": {"peak_month": 4,  "peak_day": 22, "zhr": 18,  "radiant_ra_h": 18.1, "radiant_dec_d": 33.3}},
    {"name": "Eta Aquariids", "extra_data": {"peak_month": 5,  "peak_day": 6,  "zhr": 50,  "radiant_ra_h": 22.5, "radiant_dec_d": -1.0}},
    {"name": "Delta Aquariids","extra_data": {"peak_month": 7,  "peak_day": 30, "zhr": 20,  "radiant_ra_h": 22.7, "radiant_dec_d": -16.4}},
    {"name": "Perseids",      "extra_data": {"peak_month": 8,  "peak_day": 12, "zhr": 100, "radiant_ra_h": 3.1,  "radiant_dec_d": 58.0}},
    {"name": "Draconids",     "extra_data": {"peak_month": 10, "peak_day": 8,  "zhr": 10,  "radiant_ra_h": 17.5, "radiant_dec_d": 54.0}},
    {"name": "Orionids",      "extra_data": {"peak_month": 10, "peak_day": 21, "zhr": 20,  "radiant_ra_h": 6.3,  "radiant_dec_d": 16.0}},
    {"name": "Leonids",       "extra_data": {"peak_month": 11, "peak_day": 17, "zhr": 15,  "radiant_ra_h": 10.1, "radiant_dec_d": 22.0}},
    {"name": "Geminids",      "extra_data": {"peak_month": 12, "peak_day": 14, "zhr": 150, "radiant_ra_h": 7.5,  "radiant_dec_d": 32.5}},
    {"name": "Ursids",        "extra_data": {"peak_month": 12, "peak_day": 22, "zhr": 10,  "radiant_ra_h": 14.5, "radiant_dec_d": 76.0}},
    {"name": "Taurids",       "extra_data": {"peak_month": 11, "peak_day": 5,  "zhr": 5,   "radiant_ra_h": 3.6,  "radiant_dec_d": 14.0}},
    {"name": "Puppid-Velids", "extra_data": {"peak_month": 12, "peak_day": 7,  "zhr": 10,  "radiant_ra_h": 9.0,  "radiant_dec_d": -45.0}},
]

SATELLITES = [
    {
        "name": "ISS",
        "common_name": "International Space Station",
        "obj_type": "satellite",
        "sort_order": 1,
        "extra_data": {
            "norad_id": 25544,
            "tle_source_url": "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle",
        },
    },
]


class Command(BaseCommand):
    help = "Seed the sky_catalog table from CSVs and hardcoded data"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete all rows before seeding")

    def handle(self, *args, **options):
        if options["clear"]:
            count, _ = SkyObject.objects.all().delete()
            self.stdout.write(f"Cleared {count} existing rows.")

        totals = {}

        # ── Planets ──────────────────────────────────────────────────────────
        for i, p in enumerate(PLANETS):
            obj, created = SkyObject.objects.update_or_create(
                name=p["name"], category=SkyObject.CATEGORY_PLANET,
                defaults={
                    "obj_type":   p["obj_type"],
                    "source":     "de421",
                    "sort_order": p["sort_order"],
                    "extra_data": p["extra_data"],
                    "active":     True,
                },
            )
            totals["planet"] = totals.get("planet", 0) + 1

        # ── Stars (stars.csv) ────────────────────────────────────────────────
        stars_path = os.path.join(_DATA_DIR, "stars.csv")
        with open(stars_path, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                SkyObject.objects.update_or_create(
                    name=row["name"], category=SkyObject.CATEGORY_STAR,
                    defaults={
                        "common_name": row.get("common_name", ""),
                        "obj_type":    row.get("obj_type", "star"),
                        "magnitude":   float(row["magnitude"]),
                        "ra_h":        float(row["ra_h"]),
                        "dec_d":       float(row["dec_d"]),
                        "source":      "yale_bsc",
                        "sort_order":  i,
                        "notes":       row.get("notes", ""),
                        "active":      True,
                    },
                )
                totals["star"] = totals.get("star", 0) + 1

        # ── DSOs (messier.csv) ───────────────────────────────────────────────
        messier_path = os.path.join(_DATA_DIR, "messier.csv")
        with open(messier_path, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                SkyObject.objects.update_or_create(
                    name=row["name"], category=SkyObject.CATEGORY_DSO,
                    defaults={
                        "common_name": row.get("common_name", ""),
                        "obj_type":    row.get("obj_type", ""),
                        "magnitude":   float(row["magnitude"]) if row.get("magnitude") else None,
                        "ra_h":        float(row["ra_h"]),
                        "dec_d":       float(row["dec_d"]),
                        "source":      "messier_csv",
                        "sort_order":  i,
                        "notes":       row.get("notes", ""),
                        "active":      True,
                    },
                )
                totals["dso"] = totals.get("dso", 0) + 1

        # ── Meteor Showers ───────────────────────────────────────────────────
        for i, s in enumerate(METEOR_SHOWERS):
            SkyObject.objects.update_or_create(
                name=s["name"], category=SkyObject.CATEGORY_SHOWER,
                defaults={
                    "obj_type":   "meteor_shower",
                    "source":     "static",
                    "sort_order": i,
                    "extra_data": s["extra_data"],
                    "active":     True,
                },
            )
            totals["meteor_shower"] = totals.get("meteor_shower", 0) + 1

        # ── Constellations (constellations.csv) ──────────────────────────────
        const_path = os.path.join(_DATA_DIR, "constellations.csv")
        with open(const_path, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                SkyObject.objects.update_or_create(
                    name=row["name"], category=SkyObject.CATEGORY_CONSTELLATION,
                    defaults={
                        "common_name": row.get("common_name", ""),
                        "obj_type":    row.get("obj_type", "Constellation"),
                        "ra_h":        float(row["ra_h"]),
                        "dec_d":       float(row["dec_d"]),
                        "source":      "constellations_csv",
                        "sort_order":  i,
                        "notes":       row.get("notes", ""),
                        "active":      True,
                    },
                )
                totals["constellation"] = totals.get("constellation", 0) + 1

        # ── Satellites ───────────────────────────────────────────────────────
        for i, s in enumerate(SATELLITES):
            SkyObject.objects.update_or_create(
                name=s["name"], category=SkyObject.CATEGORY_SATELLITE,
                defaults={
                    "common_name": s.get("common_name", ""),
                    "obj_type":    s.get("obj_type", "satellite"),
                    "source":      "celestrak",
                    "sort_order":  i,
                    "extra_data":  s["extra_data"],
                    "active":      True,
                },
            )
            totals["satellite"] = totals.get("satellite", 0) + 1

        self.stdout.write(self.style.SUCCESS(
            "Done. " + "  ".join(f"{cat}: {n}" for cat, n in sorted(totals.items()))
        ))
