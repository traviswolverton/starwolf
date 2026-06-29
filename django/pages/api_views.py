"""
REST API views: GET /api/v1/bortle, /api/v1/sites, /api/v1/forecast, /api/v1/sky-catalog

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
    from accounts.models import AppSetting
    return AppSetting.get("timezone", "America/Chicago")


def _ip(request):
    # Take the LAST entry in X-Forwarded-For — that's the one Cloudflare set.
    # The first entry can be spoofed by the client; only the proxy's own append is trustworthy.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


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

    from accounts.models import Site
    rows = list(Site.objects.order_by("name").values(
        "id", "name", "lat", "lon", "bortle_class", "elevation_m", "notes", "active", "site_type"
    ))
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


def _serialize_sky_object(obj):
    """Flatten DB row + extra_data into a single API-level dict."""
    base = {
        "id":          obj.id,
        "name":        obj.name,
        "common_name": obj.common_name or None,
        "category":    obj.category,
        "obj_type":    obj.obj_type or None,
        "magnitude":   obj.magnitude,
        "ra_h":        obj.ra_h,
        "dec_d":       obj.dec_d,
        "source":      obj.source or None,
        "active":      obj.active,
        "sort_order":  obj.sort_order,
        "notes":       obj.notes or None,
    }
    # Merge category-specific extra_data fields into the top level
    base.update(obj.extra_data)
    return base


def sky_catalog(request):
    if _rate_limit(f"skycatalog:{_ip(request)}", limit=60, window=60):
        return JsonResponse({"detail": "Rate limit exceeded (60/min)."}, status=429)

    from accounts.models import SkyObject

    qs = SkyObject.objects.all()

    category = request.GET.get("category")
    if category:
        valid = {c for c, _ in SkyObject.CATEGORIES}
        if category not in valid:
            return JsonResponse(
                {"detail": f"Invalid category. Must be one of: {', '.join(sorted(valid))}."},
                status=422,
            )
        qs = qs.filter(category=category)

    active_param = request.GET.get("active", "true").lower()
    if active_param == "true":
        qs = qs.filter(active=True)
    elif active_param == "false":
        qs = qs.filter(active=False)
    # "all" → no filter

    _MAX = 1000
    total = qs.count()
    objects = [_serialize_sky_object(obj) for obj in qs.order_by("category", "sort_order", "name")[:_MAX]]
    resp = {"count": len(objects), "objects": objects}
    if total > _MAX:
        resp["truncated"] = True
        resp["total"] = total
    return JsonResponse(resp)
