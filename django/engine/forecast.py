import requests
from django.core.cache import cache as django_cache

from .cache import cache_get, cache_set

OPEN_METEO_URL  = "https://api.open-meteo.com/v1/forecast"
SEVEN_TIMER_URL = "http://www.7timer.info/bin/api.pl"

OPEN_METEO_VARS = [
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "visibility", "relative_humidity_2m", "dewpoint_2m",
    "lifted_index", "cape", "wind_speed_10m",
    "precipitation_probability", "is_day",
]

# Cache TTLs
_TTL_OPEN_METEO = 3600    # 1 hour  — Open-Meteo updates hourly
_TTL_7TIMER     = 10800   # 3 hours — 7timer updates every 6h


def _fetch_open_meteo(lat: float, lon: float, forecast_days: int, timezone: str) -> dict:
    key = f"openmeteo:{lat:.4f}:{lon:.4f}:{forecast_days}:{timezone}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    # Prevent cache stampede: only one request per unique key at a time
    lock_key = f"lock:{key}"
    if not django_cache.add(lock_key, 1, 15):  # add() is atomic; fails if key exists
        # Another thread is fetching — wait briefly then return whatever is cached
        import time
        for _ in range(20):
            time.sleep(0.25)
            cached = cache_get(key)
            if cached is not None:
                return cached
        # Give up waiting and fall through to fetch anyway

    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={"latitude": lat, "longitude": lon, "hourly": OPEN_METEO_VARS,
                    "forecast_days": forecast_days, "timezone": timezone},
            timeout=10,
        )
        if not resp.ok:
            reason = resp.json().get("reason") if resp.content else None
            raise ValueError(reason or f"HTTP {resp.status_code}")
        data = resp.json()
        cache_set(key, data, _TTL_OPEN_METEO)
        return data
    finally:
        django_cache.delete(lock_key)


def _fetch_7timer(lat: float, lon: float) -> dict:
    key = f"7timer:{lat:.4f}:{lon:.4f}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    resp = requests.get(
        SEVEN_TIMER_URL,
        params={"lat": lat, "lon": lon, "product": "astro", "output": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    cache_set(key, data, _TTL_7TIMER)
    return data


def fetch_site_forecast(site: dict, forecast_days: int, timezone: str) -> dict:
    """Fetch Open-Meteo and 7timer forecasts for a single site.

    Returns a dict with keys:
      site        — the site record
      open_meteo  — raw Open-Meteo hourly response (or None on failure)
      seven_timer — raw 7timer dataseries response (or None on failure)
      errors      — list of error strings for any failed fetch
    """
    result = {"site": site, "open_meteo": None, "seven_timer": None, "errors": []}

    try:
        result["open_meteo"] = _fetch_open_meteo(site["lat"], site["lon"], forecast_days, timezone)
    except Exception as e:
        result["errors"].append(f"Open-Meteo: {e}")

    try:
        result["seven_timer"] = _fetch_7timer(site["lat"], site["lon"])
    except Exception as e:
        result["errors"].append(f"7timer: {e}")

    return result


