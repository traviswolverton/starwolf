import hashlib
import json
import math
import re
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown as md
import requests as http
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from timezonefinder import TimezoneFinder

from accounts.models import UserPreferences
from ai_summary import get_cached_summary, is_ollama_available
from bortle_lookup import lookup_bortle
from forecast import _fetch_open_meteo, fetch_site_forecast
from scorer import score_forecast, score_all

_tf = TimezoneFinder()

_COMMON_TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Anchorage", "Pacific/Honolulu", "America/Phoenix", "America/Toronto",
    "America/Vancouver", "America/Edmonton", "America/Halifax",
    "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Australia/Sydney", "Pacific/Auckland", "UTC",
]

_FEEDBACK_LIMIT = 3
_FEEDBACK_TTL = 24 * 3600

_BORTLE_DESC = {
    1: ("Excellent dark sky",             "Zodiacal light, gegenschein, and zodiacal band all visible. M33 is a direct-vision object. Scorpius and Sagittarius cast shadows."),
    2: ("Truly dark site",                "Airglow weakly visible. M33 easily seen. Limiting magnitude ~7.1–7.5."),
    3: ("Rural sky",                      "Some light pollution on the horizon. Milky Way shows tremendous structure. Limiting magnitude ~6.6–7.0."),
    4: ("Rural / suburban transition",    "Light domes visible in several directions. Milky Way still impressive but lacks fine detail. Limiting magnitude ~6.1–6.5."),
    5: ("Suburban sky",                   "Only hints of the Milky Way visible toward zenith. Light pollution obvious in most directions. Limiting magnitude ~5.6–6.0."),
    6: ("Bright suburban sky",            "Milky Way only visible near zenith. M33 invisible. Limiting magnitude ~5.1–5.5."),
    7: ("Suburban / urban transition",    "Milky Way barely visible. Clouds are brighter than the sky. Limiting magnitude ~4.6–5.0."),
    8: ("City sky",                       "Sky is orange/grey. Stars barely visible. Limiting magnitude ~4.1–4.5."),
    9: ("Inner-city sky",                 "Entire sky is bright. Only the brightest stars visible. Limiting magnitude <4.0."),
}

_BORTLE_COLOR = {
    1: "#1a1a3e", 2: "#1a2a4e", 3: "#1e3a5f",
    4: "#2e5a3f", 5: "#6e7a1f", 6: "#8e6a0f",
    7: "#9e4a0f", 8: "#ae2a0f", 9: "#be0a0f",
}


def _geocode(address):
    try:
        r = http.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "StarWolf-App/1.0"},
            timeout=10,
        )
        results = r.json()
        if not results:
            return None, None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        return None, None


def _ip_hash(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    if not ip or ip in ("127.0.0.1", "::1"):
        return None
    return hashlib.sha256((settings.IP_HASH_SALT + ip).encode()).hexdigest()


def about(request):
    return render(request, "pages/about.html")


@require_http_methods(["GET", "POST"])
def location(request):
    if not request.user.is_authenticated:
        return redirect("home")

    prefs = request.prefs

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "clear":
            prefs.location_lat = None
            prefs.location_lon = None
            prefs.location_display = ""
            prefs.location_text = ""
            prefs.timezone_auto = False
            prefs.save()
            return HttpResponse('<div class="alert success">Location cleared.</div>')

        # Set by address or by coordinates (from browser geolocation)
        lat = request.POST.get("lat")
        lon = request.POST.get("lon")
        address = request.POST.get("address", "").strip()

        if lat and lon:
            # Browser geolocation or direct coords — reverse geocode for display
            try:
                lat, lon = float(lat), float(lon)
            except ValueError:
                return HttpResponse('<div class="alert error">Invalid coordinates.</div>')
            try:
                resp = http.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={"lat": lat, "lon": lon, "format": "json"},
                    headers={"User-Agent": "StarWolf-App/1.0"},
                    timeout=8,
                )
                data = resp.json()
                addr = data.get("address", {})
                parts = [
                    addr.get("city") or addr.get("town") or addr.get("village"),
                    addr.get("state"),
                    addr.get("country_code", "").upper(),
                ]
                display = ", ".join(p for p in parts if p) or f"{lat:.4f}, {lon:.4f}"
            except Exception:
                display = f"{lat:.4f}, {lon:.4f}"
            text = display
        elif address:
            # Geocode the address
            try:
                r = http.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": address, "format": "json", "limit": 1},
                    headers={"User-Agent": "StarWolf-App/1.0"},
                    timeout=8,
                )
                results = r.json()
                if not results:
                    return HttpResponse('<div class="alert error">Address not found. Try a more specific location.</div>')
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                display = results[0].get("display_name", address)
                # Shorten: first two comma-separated parts
                parts = [p.strip() for p in display.split(",")]
                display = ", ".join(parts[:3])
                text = address
            except Exception as e:
                return HttpResponse(f'<div class="alert error">Lookup failed: {e}</div>')
        else:
            return HttpResponse('<div class="alert error">No location provided.</div>')

        tz = _tf.timezone_at(lat=lat, lng=lon) or "America/Chicago"
        prefs.location_lat = lat
        prefs.location_lon = lon
        prefs.location_display = display
        prefs.location_text = text
        prefs.timezone = tz
        prefs.timezone_auto = True
        prefs.save()

        return HttpResponse(
            f'<div class="alert success">📍 Location set to <strong>{display}</strong> '
            f'(timezone: {tz}).</div>'
            f'<script>window.dispatchEvent(new CustomEvent("location-updated"));</script>'
        )

    return render(request, "pages/location.html")


@require_http_methods(["GET", "POST"])
def preferences(request):
    if not request.user.is_authenticated:
        return redirect("home")

    prefs = request.prefs

    if request.method == "POST":
        try:
            prefs.units = request.POST.get("units", "metric")
            tz = request.POST.get("timezone", "America/Chicago")
            if tz != prefs.timezone:
                prefs.timezone_auto = False
            prefs.timezone = tz
            prefs.min_score_threshold = int(request.POST.get("min_score_threshold", 40))
            prefs.disq_max_cloud_cover = int(request.POST.get("disq_max_cloud_cover", 85))
            prefs.disq_max_precip_prob = int(request.POST.get("disq_max_precip_prob", 40))
            prefs.disq_min_visibility_km = int(request.POST.get("disq_min_visibility_km", 10))
            prefs.save()
            return HttpResponse('<div class="alert success">Preferences saved.</div>')
        except Exception as e:
            return HttpResponse(f'<div class="alert error">Save failed: {e}</div>')

    # Load scoring weights for display
    with connection.cursor() as cur:
        cur.execute("SELECT factor, weight, description FROM scoring_weights ORDER BY weight DESC")
        tel_weights = cur.fetchall()
        cur.execute("SELECT factor, weight FROM naked_eye_weights ORDER BY weight DESC")
        eye_weights = cur.fetchall()

    _factor_labels = {
        "cloud_cover": "Cloud Cover", "high_cloud": "High Cloud",
        "moon": "Moon", "lifted_index": "Stability (LI)", "humidity": "Humidity",
    }
    tel_rows = [{"factor": _factor_labels.get(r[0], r[0]), "weight": f"{r[1]*100:.0f}%", "notes": r[2]} for r in tel_weights]
    eye_desc  = {r[0]: r[2] for r in tel_weights}
    eye_rows  = [{"factor": _factor_labels.get(r[0], r[0]), "weight": f"{r[1]*100:.0f}%", "notes": eye_desc.get(r[0], "")} for r in eye_weights]

    tz_options = list(_COMMON_TIMEZONES)
    if prefs.timezone not in tz_options:
        tz_options.insert(0, prefs.timezone)

    return render(request, "pages/preferences.html", {
        "tz_options": tz_options,
        "tel_rows": tel_rows,
        "eye_rows": eye_rows,
    })


@require_http_methods(["POST"])
def preferences_reset(request):
    if not request.user.is_authenticated:
        return HttpResponse(status=403)
    prefs = request.prefs
    prefs.units = "metric"
    prefs.min_score_threshold = 40
    prefs.disq_max_cloud_cover = 85
    prefs.disq_max_precip_prob = 40
    prefs.disq_min_visibility_km = 10
    # Re-detect timezone from location if available
    if prefs.has_location:
        tz = _tf.timezone_at(lat=prefs.location_lat, lng=prefs.location_lon)
        if tz:
            prefs.timezone = tz
            prefs.timezone_auto = True
    prefs.save()
    return redirect("preferences")


_KM_TO_MI = 0.621371

_SITE_TYPE_LABELS = {
    "ida_certified":  "IDA Certified",
    "state_park":     "State Park",
    "national_park":  "National Park",
    "national_forest":"National Forest",
    "observatory":    "Observatory",
    "private":        "Private",
    "community":      "Community",
}

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


@require_http_methods(["GET"])
def sites(request):
    prefs = request.prefs
    has_loc = bool(prefs and prefs.has_location)
    is_imperial = prefs and prefs.units == "imperial"
    dist_unit = "mi" if is_imperial else "km"

    # ── Filters from query string ─────────────────────────────────────────────
    type_filter  = request.GET.get("type", "")
    try:
        bortle_max = min(9, max(1, int(request.GET.get("bortle_max", 9))))
    except ValueError:
        bortle_max = 9
    try:
        max_dist = int(request.GET.get("max_dist", 0)) or None
    except ValueError:
        max_dist = None
    sort = request.GET.get("sort", "dist" if has_loc else "name")
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        page = 1

    # ── DB query ──────────────────────────────────────────────────────────────
    sql = "SELECT id, name, lat, lon, bortle_class, elevation_m, notes, site_type FROM sites WHERE active=1"
    params = []
    if type_filter:
        sql += " AND site_type = %s"
        params.append(type_filter)
    if bortle_max < 9:
        sql += " AND bortle_class <= %s"
        params.append(bortle_max)
    sql += " ORDER BY name"

    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]

    # ── Distance + display enrichment ─────────────────────────────────────────
    for row in rows:
        row["type_label"] = _SITE_TYPE_LABELS.get(row["site_type"] or "", row["site_type"] or "—")
        row["bortle_color"] = _BORTLE_COLOR.get(row["bortle_class"] or 5, "#555")
        row["map_url"] = (
            f"https://www.openstreetmap.org/?mlat={row['lat']}&mlon={row['lon']}"
            f"#map=12/{row['lat']}/{row['lon']}"
        )
        if has_loc:
            km = _haversine(prefs.location_lat, prefs.location_lon, row["lat"], row["lon"])
            row["dist_km"] = km
            row["dist_display"] = f"{km * _KM_TO_MI:.0f} {dist_unit}" if is_imperial else f"{km:.0f} {dist_unit}"

    # ── Filter by distance ────────────────────────────────────────────────────
    if has_loc and max_dist:
        max_km = max_dist / _KM_TO_MI if is_imperial else max_dist
        rows = [r for r in rows if r["dist_km"] <= max_km]

    # ── Sort ──────────────────────────────────────────────────────────────────
    if sort == "dist" and has_loc:
        rows.sort(key=lambda r: r["dist_km"])
    elif sort == "bortle":
        rows.sort(key=lambda r: r["bortle_class"] or 9)

    # ── Paginate ──────────────────────────────────────────────────────────────
    per_page = 50
    total = len(rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    page_rows = rows[(page - 1) * per_page : page * per_page]

    ctx = {
        "rows": page_rows,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "type_filter": type_filter,
        "bortle_max": bortle_max,
        "max_dist": max_dist or "",
        "sort": sort,
        "has_loc": has_loc,
        "dist_unit": dist_unit,
        "site_types": _SITE_TYPE_LABELS,
        "page_range": range(max(1, page - 2), min(total_pages + 1, page + 3)),
    }

    if request.headers.get("HX-Request"):
        return render(request, "pages/_sites_rows.html", ctx)
    return render(request, "pages/sites.html", ctx)


_CDT = ZoneInfo("America/Chicago")
_COMPUTE_WORKERS = 5
_COMPUTE_STATE_KEY = "heatmap:compute_state"


def _score_to_color(score):
    if score is None:
        return "#969696"
    s = max(0.0, min(100.0, float(score)))
    if s >= 50:
        t = (s - 50) / 50
        r = int(220 - 170 * t)
        g = 200
        b = int(55 * t)
    else:
        t = s / 50
        r = 220
        g = int(50 + 150 * t)
        b = int(50 - 50 * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _score_one_site(site, tz):
    try:
        om = _fetch_open_meteo(site["lat"], site["lon"], forecast_days=2, timezone=tz)
        nights = score_forecast(
            {"site": site, "open_meteo": om, "seven_timer": None, "errors": []},
            tz_str=tz,
        )
        return nights[0]["composite"] if nights else None
    except Exception:
        return None


def _run_compute(today, tz, only_missing=False):
    """Background thread: score all sites and upsert into site_daily_scores."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with connection.cursor() as cur:
        if only_missing:
            cur.execute("""
                SELECT s.id, s.name, s.lat, s.lon, s.bortle_class
                FROM sites s
                LEFT JOIN site_daily_scores sd
                    ON sd.site_id = s.id AND sd.score_date = %s
                WHERE s.active = 1 AND sd.score IS NULL
            """, [today])
        else:
            cur.execute(
                "SELECT id, name, lat, lon, bortle_class FROM sites WHERE active = 1"
            )
        cols = [d[0] for d in cur.description]
        sites = [dict(zip(cols, row)) for row in cur.fetchall()]

    total = len(sites)
    done = 0
    batch = []

    cache.set(_COMPUTE_STATE_KEY, {"running": True, "done": 0, "total": total}, 600)

    with ThreadPoolExecutor(max_workers=_COMPUTE_WORKERS) as executor:
        futures = {executor.submit(_score_one_site, s, tz): s for s in sites}
        for future in as_completed(futures):
            site = futures[future]
            score = future.result()
            done += 1
            batch.append({
                "site_id": site["id"], "name": site["name"],
                "lat": site["lat"], "lon": site["lon"],
                "score": score, "date": today,
            })
            if len(batch) >= 50 or done == total:
                with connection.cursor() as cur:
                    for row in batch:
                        cur.execute("""
                            INSERT INTO site_daily_scores
                                (site_id, score_date, name, lat, lon, score)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (site_id, score_date) DO UPDATE SET
                                score = EXCLUDED.score, computed_at = NOW()
                        """, [row["site_id"], row["date"], row["name"],
                              row["lat"], row["lon"], row["score"]])
                batch = []
            if done % 50 == 0 or done == total:
                cache.set(_COMPUTE_STATE_KEY, {"running": True, "done": done, "total": total}, 600)

    cache.set(_COMPUTE_STATE_KEY, {"running": False, "done": done, "total": total}, 60)


def _today_local():
    return datetime.now(_CDT).date().isoformat()


def _load_heatmap_data(today):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT name, lat, lon, score, computed_at
            FROM site_daily_scores
            WHERE score_date = %s
            ORDER BY score DESC NULLS LAST
        """, [today])
        rows = cur.fetchall()
    if not rows:
        return None, None
    sites = []
    scored = 0
    computed_at = None
    for name, lat, lon, score, ts in rows:
        sites.append({
            "name": name, "lat": lat, "lon": lon,
            "score": round(score) if score is not None else None,
            "color": _score_to_color(score),
        })
        if score is not None:
            scored += 1
        if computed_at is None and ts is not None:
            computed_at = ts
    return sites, {"total": len(sites), "scored": scored, "computed_at": computed_at}


@require_http_methods(["GET"])
def heatmap(request):
    today = _today_local()
    sites, meta = _load_heatmap_data(today)
    compute_state = cache.get(_COMPUTE_STATE_KEY)
    is_admin = request.user.is_authenticated and request.user.is_admin()

    ts_str = None
    if meta and meta["computed_at"]:
        ts = meta["computed_at"]
        if hasattr(ts, "astimezone"):
            ts_str = ts.astimezone(_CDT).strftime("%-I:%M %p CDT")

    return render(request, "pages/heatmap.html", {
        "sites_json": json.dumps(sites or []),
        "meta": meta,
        "ts_str": ts_str,
        "today": today,
        "has_data": bool(sites),
        "is_admin": is_admin,
        "compute_state": compute_state,
    })


@require_http_methods(["POST"])
def heatmap_compute(request):
    if not (request.user.is_authenticated and request.user.is_admin()):
        return JsonResponse({"error": "Admin only"}, status=403)

    state = cache.get(_COMPUTE_STATE_KEY)
    if state and state.get("running"):
        return JsonResponse({"status": "already_running", **state})

    only_missing = request.POST.get("only_missing") == "1"
    today = _today_local()
    # Use UTC timezone from DB settings as fallback
    with connection.cursor() as cur:
        cur.execute("SELECT value FROM app_settings WHERE key = 'timezone'")
        row = cur.fetchone()
    tz = row[0] if row else "America/Chicago"

    t = threading.Thread(
        target=_run_compute, args=(today, tz, only_missing), daemon=True
    )
    t.start()
    return JsonResponse({"status": "started"})


@require_http_methods(["GET"])
def heatmap_status(request):
    if not (request.user.is_authenticated and request.user.is_admin()):
        return JsonResponse({"error": "Admin only"}, status=403)
    state = cache.get(_COMPUTE_STATE_KEY) or {"running": False}
    return JsonResponse(state)


@require_http_methods(["GET", "POST"])
def bortle_scorer(request):
    if request.method == "GET":
        return render(request, "pages/bortle_scorer.html")

    # ── Resolve lat/lon ───────────────────────────────────────────────────────
    address = request.POST.get("address", "").strip()
    if address:
        lat, lon = _geocode(address)
        if lat is None:
            return HttpResponse('<div class="alert error">Address not found. Try a more specific location or use coordinates.</div>')
    else:
        try:
            lat = float(request.POST.get("lat", ""))
            lon = float(request.POST.get("lon", ""))
        except ValueError:
            return HttpResponse('<div class="alert error">Invalid coordinates.</div>')

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return HttpResponse('<div class="alert error">Coordinates out of range.</div>')

    # ── Bortle lookup ─────────────────────────────────────────────────────────
    try:
        data = lookup_bortle(lat, lon)
    except FileNotFoundError:
        return HttpResponse('<div class="alert error">World Atlas GeoTIFF is not available on this server.</div>')
    except ValueError as e:
        return HttpResponse(f'<div class="alert error">No data for this location: {e}</div>')

    bortle = data["bortle"]
    sqm    = data["sqm"]
    label, desc = _BORTLE_DESC[bortle]
    color  = _BORTLE_COLOR[bortle]

    return render(request, "pages/_bortle_result.html", {
        "bortle": bortle, "sqm": sqm, "label": label,
        "desc": desc, "color": color, "lat": lat, "lon": lon,
    })


@require_http_methods(["GET", "POST"])
def feedback(request):
    if request.method == "GET":
        return render(request, "pages/feedback.html")

    # ── POST: validate ────────────────────────────────────────────────────────
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    submitter = request.POST.get("submitter", "").strip()
    feedback_type = request.POST.get("type", "feature")

    if not title or not description:
        return HttpResponse('<div class="alert error">Title and description are required.</div>')

    # ── Rate limit ────────────────────────────────────────────────────────────
    ip_hash = _ip_hash(request)
    if ip_hash and cache.get(f"feedback:{ip_hash}", 0) >= _FEEDBACK_LIMIT:
        return HttpResponse(
            f'<div class="alert warning">You\'ve submitted {_FEEDBACK_LIMIT} items in the '
            f'past 24 hours. Please check back tomorrow.</div>'
        )

    # ── GitHub API ────────────────────────────────────────────────────────────
    token = settings.GITHUB_TOKEN
    if not token:
        return HttpResponse('<div class="alert error">Feedback is not configured. Contact the site owner.</div>')

    prefix = "[Feature Request]" if feedback_type == "feature" else "[Bug Report]"
    body = (f"**Submitted by:** {submitter}\n\n" if submitter else "") + description

    try:
        resp = http.post(
            f"https://api.github.com/repos/{settings.GITHUB_REPO}/issues",
            json={"title": f"{prefix} {title}", "body": body},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )
    except http.exceptions.Timeout:
        return HttpResponse('<div class="alert error">Request timed out. Try again.</div>')
    except Exception as e:
        return HttpResponse(f'<div class="alert error">Submission failed: {e}</div>')

    if resp.status_code != 201:
        return HttpResponse(f'<div class="alert error">Submission failed (HTTP {resp.status_code}). Try again.</div>')

    issue = resp.json()
    if ip_hash:
        cache.set(f"feedback:{ip_hash}", cache.get(f"feedback:{ip_hash}", 0) + 1, _FEEDBACK_TTL)

    label = "feature request" if feedback_type == "feature" else "bug report"
    return HttpResponse(
        f'<div class="alert success">'
        f'Thanks! Your {label} was submitted as '
        f'<a href="{issue["html_url"]}" target="_blank">issue #{issue["number"]}</a>.'
        f'</div>'
    )


# ── Planner helpers ───────────────────────────────────────────────────────────

def _norm(value, lo, hi, higher_is_better=True):
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        return None
    n = (max(lo, min(hi, float(value))) - lo) / (hi - lo)
    return n if higher_is_better else 1 - n


def _metric_color(norm):
    if norm is None:
        return "#444"
    hue = int(norm * 120)
    return f"hsl({hue}, 70%, 38%)"


def _fmt_val(value, fmt=".0f", suffix="", fallback="—"):
    if value is None:
        return fallback
    try:
        if math.isnan(float(value)):
            return fallback
    except (TypeError, ValueError):
        return fallback
    return f"{value:{fmt}}{suffix}"


def _heatmap_bg(score, threshold):
    if score is None:
        return "#1a1d27"
    if score < threshold:
        return "#1e1616"
    t = (score - threshold) / max(1, 100 - threshold)
    hue = int(t * 120)
    return f"hsl({hue}, 55%, 28%)"


def _enrich_night(night, prefs, site_coords):
    stats = night.get("stats", {})
    factors = night.get("factors", {})
    lat, lon = site_coords.get(night["site"], (None, None))
    dist_str = ""
    if prefs and prefs.has_location and lat is not None:
        km = _haversine(prefs.location_lat, prefs.location_lon, lat, lon)
        dist_str = f"{km * _KM_TO_MI:.0f} mi" if prefs.units == "imperial" else f"{km:.0f} km"
    bortle = stats.get("bortle_class")
    metrics = [
        {"label": "Cloud Cover", "value": _fmt_val(stats.get("avg_cloud_cover"), suffix="%"),  "color": _metric_color(_norm(stats.get("avg_cloud_cover"),      0, 100, False))},
        {"label": "High Cloud",  "value": _fmt_val(stats.get("avg_high_cloud"),  suffix="%"),  "color": _metric_color(_norm(stats.get("avg_high_cloud"),        0, 100, False))},
        {"label": "Moon Score",  "value": _fmt_val(factors.get("moon")),                       "color": _metric_color(_norm(factors.get("moon"),                0, 100, True))},
        {"label": "Night Hours", "value": _fmt_val(stats.get("night_hours"), ".0f", "h"),      "color": _metric_color(_norm(stats.get("night_hours"),           4,  12, True))},
        {"label": "Humidity",    "value": _fmt_val(stats.get("avg_humidity"), suffix="%"),     "color": _metric_color(_norm(stats.get("avg_humidity"),          0, 100, False))},
        {"label": "Stability",   "value": _fmt_val(factors.get("lifted_index")),               "color": _metric_color(_norm(factors.get("lifted_index"),        0, 100, True))},
        {"label": "Seeing †",    "value": _fmt_val(stats.get("seeing_7timer"), ".1f"),         "color": _metric_color(_norm(stats.get("seeing_7timer"),         1,   8, False))},
        {"label": "Transp. †",   "value": _fmt_val(stats.get("transparency_7timer"), ".1f"),  "color": _metric_color(_norm(stats.get("transparency_7timer"),   1,   8, False))},
        {"label": "Bortle",      "value": f"Class {bortle}" if bortle else "—",               "color": _metric_color(_norm(bortle,                             1,   9, False))},
    ]
    date_obj = datetime.fromisoformat(night["date"])
    composite = night.get("composite") or 0
    naked_eye = night.get("naked_eye")
    tel_norm = _norm(composite, 0, 100, True) or 0
    eye_norm = _norm(naked_eye, 0, 100, True) if naked_eye is not None else None
    map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=12/{lat}/{lon}" if lat else ""
    return {
        **night,
        "date_str":    date_obj.strftime("%a %-d %b"),
        "dist_str":    dist_str,
        "metrics":     metrics,
        "tel_score":   round(composite),
        "eye_score":   round(naked_eye) if naked_eye is not None else None,
        "tel_color":   f"hsl({int(tel_norm * 120)}, 70%, 42%)",
        "eye_color":   f"hsl({int(eye_norm * 120)}, 70%, 42%)" if eye_norm is not None else "#555",
        "map_url":     map_url,
    }


def _build_heatmap(nights, threshold, score_key="composite"):
    scored = [n for n in nights if not n.get("disqualified")]
    sites = sorted(set(n["site"] for n in scored))
    dates = sorted(set(n["date"] for n in scored))
    lookup = {(n["site"], n["date"]): n.get(score_key) for n in scored}
    rows = []
    for site in sites:
        cells = []
        for date in dates:
            score = lookup.get((site, date))
            cells.append({
                "score": round(score) if score is not None else None,
                "bg": _heatmap_bg(score, threshold),
            })
        rows.append({"site": site, "cells": cells})
    date_labels = [datetime.fromisoformat(d).strftime("%-d %b") for d in dates]
    return {"rows": rows, "dates": date_labels}


def _load_planner_sites(prefs, max_dist_km=None):
    with connection.cursor() as cur:
        cur.execute("SELECT id, name, lat, lon, bortle_class, site_type FROM sites WHERE active=1")
        cols = [d[0] for d in cur.description]
        all_sites = [dict(zip(cols, r)) for r in cur.fetchall()]
    if prefs and prefs.has_location and max_dist_km:
        return [
            s for s in all_sites
            if _haversine(prefs.location_lat, prefs.location_lon, s["lat"], s["lon"]) <= max_dist_km
        ]
    return all_sites


def _run_planner_thread(user_id, sites, forecast_days, tz, disq):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    state_key   = f"planner:status:{user_id}"
    results_key = f"planner:nights:{user_id}"
    total = len(sites)
    cache.set(state_key, {"running": True, "done": 0, "total": total}, 600)
    forecasts = []
    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fetch_site_forecast, s, forecast_days, tz): s for s in sites}
        for future in as_completed(futures):
            try:
                forecasts.append(future.result())
            except Exception:
                pass
            done += 1
            if done % 10 == 0 or done == total:
                cache.set(state_key, {"running": True, "done": done, "total": total}, 600)
    nights = score_all(forecasts, tz, disq)
    cache.set(results_key, json.dumps(nights), 7200)
    cache.set(state_key, {"running": False, "done": done, "total": total}, 120)


def _get_planner_max_sites():
    with connection.cursor() as cur:
        cur.execute("SELECT value FROM app_settings WHERE key = 'planner_max_sites'")
        row = cur.fetchone()
    return int(row[0]) if row else 250


@require_http_methods(["GET"])
def planner(request):
    prefs = request.prefs

    try:
        radius_val = int(request.GET.get("radius", 300))
    except ValueError:
        radius_val = 300

    is_imperial = prefs and prefs.units == "imperial"
    dist_unit_str = "mi" if is_imperial else "km"
    radius_km = radius_val / _KM_TO_MI if is_imperial else radius_val

    sites = _load_planner_sites(prefs, radius_km if (prefs and prefs.has_location) else None)
    max_sites = _get_planner_max_sites()
    site_count = len(sites)

    state_key   = f"planner:status:{request.user.pk}"
    results_key = f"planner:nights:{request.user.pk}"
    compute_state = cache.get(state_key)
    cached_nights_json = cache.get(results_key)

    return render(request, "pages/planner.html", {
        "prefs":           prefs,
        "site_count":      site_count,
        "effective_count": min(site_count, max_sites),
        "max_sites":       max_sites,
        "capped":          site_count > max_sites,
        "radius_val":      radius_val,
        "dist_unit":       dist_unit_str,
        "is_running":      bool(compute_state and compute_state.get("running")),
        "has_results":     bool(cached_nights_json),
        "compute_state":   compute_state,
    })


@require_http_methods(["POST"])
def planner_run(request):
    prefs = request.prefs
    if not request.user.is_authenticated:
        return HttpResponse('<div class="alert error">Login required.</div>', status=401)

    state_key = f"planner:status:{request.user.pk}"
    state = cache.get(state_key)
    if state and state.get("running"):
        return render(request, "pages/_planner_progress.html", {"compute_state": state})

    is_imperial = prefs and prefs.units == "imperial"
    try:
        radius_val = int(request.POST.get("radius", 300))
    except ValueError:
        radius_val = 300
    radius_km = radius_val / _KM_TO_MI if is_imperial else radius_val

    sites = _load_planner_sites(prefs, radius_km if (prefs and prefs.has_location) else None)
    if not sites:
        return HttpResponse('<div class="alert error">No sites found in range. Try increasing your search radius.</div>')

    # Enforce site cap — sort closest-first so the user gets their nearest sites
    max_sites = _get_planner_max_sites()
    if len(sites) > max_sites:
        if prefs and prefs.has_location:
            sites.sort(key=lambda s: _haversine(prefs.location_lat, prefs.location_lon, s["lat"], s["lon"]))
        sites = sites[:max_sites]

    with connection.cursor() as cur:
        cur.execute("SELECT value FROM app_settings WHERE key = 'forecast_days'")
        row = cur.fetchone()
    forecast_days = int(row[0]) if row else 10

    tz = prefs.timezone if prefs else "America/Chicago"
    disq = {
        "max_cloud_cover":   prefs.disq_max_cloud_cover   if prefs else 85,
        "max_precip_prob":   prefs.disq_max_precip_prob   if prefs else 40,
        "min_visibility_km": prefs.disq_min_visibility_km if prefs else 10,
    }

    threading.Thread(
        target=_run_planner_thread,
        args=(request.user.pk, sites, forecast_days, tz, disq),
        daemon=True,
    ).start()

    return render(request, "pages/_planner_progress.html", {
        "compute_state": {"running": True, "done": 0, "total": len(sites)},
    })


@require_http_methods(["GET"])
def planner_poll(request):
    state_key   = f"planner:status:{request.user.pk}"
    results_key = f"planner:nights:{request.user.pk}"
    state = cache.get(state_key) or {}

    if state.get("running"):
        return render(request, "pages/_planner_progress.html", {"compute_state": state})

    nights_json = cache.get(results_key)
    if not nights_json:
        return HttpResponse('<div class="alert warning">No results cached. Run the forecast first.</div>')

    return _render_results(request, json.loads(nights_json))


def _render_results(request, nights):
    prefs = request.prefs
    threshold = prefs.min_score_threshold if prefs else 40
    sort = request.GET.get("sort", "score")
    score_key = "naked_eye" if request.GET.get("view") == "eye" else "composite"
    today = datetime.now(ZoneInfo(prefs.timezone if prefs else "America/Chicago")).date()

    # Split scored vs disqualified
    scored = [
        n for n in nights
        if not n.get("disqualified")
        and datetime.fromisoformat(n["date"]).date() >= today
        and (n.get("composite") or 0) >= threshold
    ]
    disq = [
        n for n in nights
        if n.get("disqualified")
        and datetime.fromisoformat(n["date"]).date() >= today
    ]

    # Sort
    if sort == "date":
        scored.sort(key=lambda n: (n["date"], -(n.get("composite") or 0)))
    elif sort == "location":
        scored.sort(key=lambda n: (n["site"], n["date"]))
    elif sort == "eye":
        scored.sort(key=lambda n: -(n.get("naked_eye") or 0))
    else:
        scored.sort(key=lambda n: -(n.get("composite") or 0))

    # Enrich
    with connection.cursor() as cur:
        cur.execute("SELECT name, lat, lon FROM sites WHERE active=1")
        site_coords = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    enriched = [_enrich_night(n, prefs, site_coords) for n in scored]

    # Heatmap
    heatmap = _build_heatmap(nights, threshold, score_key)

    # AI summary
    ai_summary = None
    try:
        if scored and is_ollama_available():
            ai_summary = get_cached_summary(scored[:10])
    except Exception:
        pass

    return render(request, "pages/_planner_results.html", {
        "nights":      enriched,
        "disq":        disq,
        "heatmap":     heatmap,
        "threshold":   threshold,
        "sort":        sort,
        "score_key":   score_key,
        "ai_summary":  ai_summary,
        "total_scored":  len(scored),
        "total_disq":    len(disq),
    })


def admin_panel(request):
    from accounts.decorators import require_admin
    if not request.user.is_authenticated or not request.user.is_admin():
        return redirect("home")

    with connection.cursor() as cur:
        cur.execute("SELECT id, factor, weight, description FROM scoring_weights ORDER BY weight DESC")
        tel_weights = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        cur.execute("SELECT id, factor, weight, description FROM naked_eye_weights ORDER BY weight DESC")
        eye_weights = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        cur.execute("SELECT key, value, description FROM app_settings ORDER BY key")
        app_settings = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM sites WHERE bortle_class IS NULL")
        bortle_null_count = cur.fetchone()[0]

    return render(request, "pages/admin.html", {
        "tel_weights": tel_weights,
        "eye_weights": eye_weights,
        "app_settings": app_settings,
        "bortle_null_count": bortle_null_count,
    })


@require_http_methods(["POST"])
def admin_save_weights(request):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse('<div class="alert error">Admin only.</div>', status=403)

    table = request.POST.get("table", "scoring_weights")
    if table not in ("scoring_weights", "naked_eye_weights"):
        return HttpResponse('<div class="alert error">Invalid table.</div>', status=400)

    factors      = request.POST.getlist("factor")
    weights_raw  = request.POST.getlist("weight")
    descriptions = request.POST.getlist("description")

    try:
        weights = [float(w) for w in weights_raw]
    except ValueError:
        return HttpResponse('<div class="alert error">Weights must be numbers.</div>')

    total = sum(weights)
    if abs(total - 1.0) > 0.001:
        return HttpResponse(f'<div class="alert error">Weights sum to {total:.3f} — must equal 1.00.</div>')

    rows = [{"factor": f, "weight": w, "desc": d}
            for f, w, d in zip(factors, weights, descriptions) if f.strip()]

    with connection.cursor() as cur:
        cur.execute(f"DELETE FROM {table}")
        for row in rows:
            cur.execute(
                f"INSERT INTO {table} (factor, weight, description) VALUES (%s, %s, %s)",
                [row["factor"], row["weight"], row["desc"]]
            )

    return HttpResponse('<div class="alert success">Weights saved.</div>')


@require_http_methods(["POST"])
def admin_save_settings(request):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse('<div class="alert error">Admin only.</div>', status=403)

    keys   = request.POST.getlist("key")
    values = request.POST.getlist("value")
    descs  = request.POST.getlist("description")

    with connection.cursor() as cur:
        for key, value, desc in zip(keys, values, descs):
            if key.strip():
                cur.execute("""
                    INSERT INTO app_settings (key, value, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, [key.strip(), value, desc])

    return HttpResponse('<div class="alert success">Settings saved.</div>')


@require_http_methods(["POST"])
def admin_bortle_fill(request):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse('<div class="alert error">Admin only.</div>', status=403)

    with connection.cursor() as cur:
        cur.execute("SELECT id, name, lat, lon FROM sites WHERE bortle_class IS NULL ORDER BY name")
        cols = [d[0] for d in cur.description]
        null_sites = [dict(zip(cols, r)) for r in cur.fetchall()]

    if not null_sites:
        return HttpResponse('<div class="alert success">No sites missing Bortle — nothing to do.</div>')

    ok, failed = 0, []
    for site in null_sites:
        try:
            result = lookup_bortle(site["lat"], site["lon"])
            with connection.cursor() as cur:
                cur.execute("UPDATE sites SET bortle_class = %s WHERE id = %s",
                            [result["bortle"], site["id"]])
            ok += 1
        except Exception as e:
            failed.append(f"{site['name']}: {e}")

    msg = f'<div class="alert success">Updated {ok} site(s).</div>'
    if failed:
        msg += '<div class="alert warning">Some failed:<br>' + "<br>".join(failed) + "</div>"
    return HttpResponse(msg)


def api_guide(request):
    guide_path = Path(settings.BASE_DIR).parent / "API_GUIDE.md"
    raw = guide_path.read_text()

    parts = re.split(r"\n(?=### )", raw)

    overview_parts, endpoints = [], []
    for part in parts:
        m = re.match(r"### (.+?)\n", part)
        if m and "/" in m.group(1):
            label = m.group(1).replace("`", "")
            # Short label for the tab button: just METHOD /path
            short = re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)", label)
            endpoints.append({
                "label": label,
                "tab": short.group(0) if short else label,
                "html": md.markdown(part, extensions=["tables", "fenced_code"]),
            })
        else:
            overview_parts.append(part)

    return render(request, "pages/api_guide.html", {
        "overview_html": md.markdown(
            "\n".join(overview_parts), extensions=["tables", "fenced_code"]
        ),
        "endpoints": endpoints,
    })
