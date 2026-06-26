import hashlib
import re
from pathlib import Path

import markdown as md
import requests as http
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from timezonefinder import TimezoneFinder

from accounts.models import UserPreferences
from bortle_lookup import lookup_bortle

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
