"""
REST API views: GET /api/v1/bortle, /api/v1/sites, /api/v1/forecast

Rate limiting uses Django's cache backend (Redis).
"""
import time

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

from engine.bortle_lookup import lookup_bortle
from engine.forecast import fetch_site_forecast
from engine.scorer import score_forecast


def _rate_limit(key, limit, window):
    """Return True if request should be blocked (rate limit exceeded)."""
    now = int(time.time())
    bucket = now // window
    cache_key = f"rl:{key}:{bucket}"
    count = cache.get(cache_key, 0)
    if count >= limit:
        return True
    cache.set(cache_key, count + 1, window)
    return False


def _default_tz():
    with connection.cursor() as cur:
        cur.execute("SELECT value FROM app_settings WHERE key = 'timezone'")
        row = cur.fetchone()
    return row[0] if row else "America/Chicago"


def _ip(request):
    return (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "unknown")
    )


def bortle(request):
    if _rate_limit(f"bortle:{_ip(request)}", limit=60, window=60):
        return JsonResponse({"detail": "Rate limit exceeded (60/min)."}, status=429)

    try:
        lat = float(request.GET["lat"])
        lon = float(request.GET["lon"])
    except (KeyError, ValueError):
        return JsonResponse({"detail": "lat and lon are required numeric parameters."}, status=422)

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return JsonResponse({"detail": "lat must be -90–90 and lon must be -180–180."}, status=422)

    try:
        result = lookup_bortle(lat, lon)
    except FileNotFoundError:
        return JsonResponse({"detail": "World Atlas GeoTIFF not available on this server."}, status=503)
    except ValueError as e:
        return JsonResponse({"detail": str(e)}, status=422)

    return JsonResponse(result)


def sites(request):
    if _rate_limit(f"sites:{_ip(request)}", limit=10, window=60):
        return JsonResponse({"detail": "Rate limit exceeded (10/min)."}, status=429)

    with connection.cursor() as cur:
        cur.execute(
            "SELECT id, name, lat, lon, bortle_class, elevation_m, notes, active, site_type "
            "FROM sites ORDER BY name"
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    return JsonResponse({"count": len(rows), "sites": rows})


def forecast(request):
    if _rate_limit(f"forecast:{_ip(request)}", limit=30, window=60):
        return JsonResponse({"detail": "Rate limit exceeded (30/min)."}, status=429)

    try:
        lat = float(request.GET["lat"])
        lon = float(request.GET["lon"])
    except (KeyError, ValueError):
        return JsonResponse({"detail": "lat and lon are required numeric parameters."}, status=422)

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return JsonResponse({"detail": "lat must be -90–90 and lon must be -180–180."}, status=422)

    try:
        days = int(request.GET.get("days", 7))
    except ValueError:
        return JsonResponse({"detail": "'days' must be an integer."}, status=422)

    if not (1 <= days <= 16):
        return JsonResponse({"detail": "'days' must be between 1 and 16."}, status=422)

    bortle_class = request.GET.get("bortle_class")
    if bortle_class is not None:
        try:
            bortle_class = int(bortle_class)
        except ValueError:
            return JsonResponse({"detail": "'bortle_class' must be an integer 1–9."}, status=422)
        if not (1 <= bortle_class <= 9):
            return JsonResponse({"detail": "'bortle_class' must be between 1 and 9."}, status=422)

    tz = request.GET.get("timezone") or _default_tz()

    site = {"name": f"{lat:.4f},{lon:.4f}", "lat": lat, "lon": lon, "bortle_class": bortle_class}

    fc = fetch_site_forecast(site, days, tz)

    if fc["open_meteo"] is None:
        om_errors = [e for e in fc.get("errors", []) if e.startswith("Open-Meteo")]
        detail = om_errors[0] if om_errors else "Open-Meteo forecast unavailable"
        return JsonResponse({"detail": detail}, status=502)

    nights = score_forecast(fc, tz)

    return JsonResponse({
        "lat": lat,
        "lon": lon,
        "timezone": tz,
        "days": days,
        "nights": nights,
        "errors": fc.get("errors", []),
    })
