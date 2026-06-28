"""Load and cache the Messier catalog from the bundled CSV."""
import csv
from pathlib import Path

_CSV_PATH = Path(__file__).parent / "data" / "messier.csv"
_catalog = None


def load_catalog() -> list[dict]:
    global _catalog
    if _catalog is not None:
        return _catalog
    rows = []
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "name":        row["name"],
                "ra_h":        float(row["ra_h"]),
                "dec_d":       float(row["dec_d"]),
                "magnitude":   float(row["magnitude"]),
                "obj_type":    row["obj_type"],
                "common_name": row["common_name"],
                "notes":       row["notes"],
            })
    _catalog = rows
    return _catalog
