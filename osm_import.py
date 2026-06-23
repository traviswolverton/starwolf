import json
import math
import requests
from pathlib import Path
from db import get_connection

NOMINATIM_URL  = "https://nominatim.openstreetmap.org/search"
_HEADERS       = {"User-Agent": "stargazing-app/1.0"}
_DATASET_PATH  = Path(__file__).parent / "dark_sky_sites.json"


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


_GEOGRATIS_URL = "https://geogratis.gc.ca/services/geolocation/en/locate"
_CA_POSTAL_RE  = __import__("re").compile(r"^[A-Za-z]\d[A-Za-z][ ]?\d[A-Za-z]\d$")


def geocode(query: str) -> tuple[float, float, str]:
    q = query.strip()

    # Canadian postal codes: use GeoGratis (Nominatim doesn't support them)
    if _CA_POSTAL_RE.match(q):
        resp = requests.get(_GEOGRATIS_URL, params={"q": q}, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        for result in resp.json():
            if result.get("type", "").endswith("PostalCode"):
                lon, lat = result["geometry"]["coordinates"]
                return float(lat), float(lon), result["title"] + ", Canada"
        raise ValueError(f"No location found for Canadian postal code '{q}'")

    resp = requests.get(NOMINATIM_URL, params={"q": q, "format": "json", "limit": 1}, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"No location found for '{q}'")
    r = results[0]
    return float(r["lat"]), float(r["lon"]), r["display_name"]


def search_dark_sky_sites(lat: float, lon: float, radius_km: float) -> list[dict]:
    with open(_DATASET_PATH) as f:
        all_sites = json.load(f)

    results = []
    for site in all_sites:
        dist = _haversine(lat, lon, site["lat"], site["lon"])
        if dist <= radius_km:
            results.append({**site, "distance_km": round(dist, 1)})

    results.sort(key=lambda x: x["distance_km"])
    return results[:10]


def find_nearest_existing(lat: float, lon: float) -> tuple[str, float] | None:
    """Returns (name, distance_km) of nearest DB site within 10 km, or None."""
    con = get_connection()
    rows = con.execute("SELECT name, lat, lon FROM sites").fetchall()
    con.close()
    best_name, best_dist = None, float("inf")
    for name, slat, slon in rows:
        d = _haversine(lat, lon, slat, slon)
        if d < best_dist:
            best_dist, best_name = d, name
    if best_dist < 10:
        return best_name, round(best_dist, 1)
    return None


def import_sites(sites: list[dict]) -> int:
    con = get_connection()
    cur = con.cursor()
    for s in sites:
        cur.execute(
            "INSERT INTO sites (name, lat, lon, elevation_m, notes, active) VALUES (?,?,?,?,?,1)",
            (s["name"], s["lat"], s["lon"], s.get("elevation_m"), s.get("notes")),
        )
    con.commit()
    con.close()
    return len(sites)
