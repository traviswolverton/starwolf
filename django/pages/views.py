import hashlib
import json
import logging
import math
import re
import threading

_log = logging.getLogger(__name__)
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown as md
import requests as http
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from timezonefinder import TimezoneFinder

from accounts.models import UserPreferences
from engine.ai_summary import get_cached_summary, is_ollama_available
from engine.bortle_lookup import lookup_bortle
from engine.forecast import _fetch_open_meteo, fetch_site_forecast
from engine.scorer import score_forecast, score_all

_tf = TimezoneFinder()

# Houston city-center coordinates used for guest planner sessions
_GUEST_LAT  = 29.7604
_GUEST_LON  = -95.3698
_GUEST_DISP = "Houston, TX (guest)"
_GUEST_TZ   = "America/Chicago"


class _GuestPrefs:
    """Lightweight prefs stand-in for unauthenticated planner sessions."""
    has_location       = True
    location_lat       = _GUEST_LAT
    location_lon       = _GUEST_LON
    location_display   = _GUEST_DISP
    units              = "imperial"
    timezone           = _GUEST_TZ
    min_score_threshold   = 40
    disq_max_cloud_cover  = 85
    disq_max_precip_prob  = 40
    disq_min_visibility_km = 10
    best_metric           = "combined"


def _planner_key_prefix(request):
    """Returns a stable cache key prefix for the current user or session."""
    if request.user.is_authenticated:
        return str(request.user.pk)
    return f"guest:{request.session.session_key or 'anon'}"

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


_MOON_PHASES = [
    {
        "emoji": "🌑", "name": "New Moon",
        "day_range": (0, 1.84),
        "desc": "The Moon sits between Earth and the Sun. Its illuminated side faces away from us — the sky is as dark as it gets. Perfect for deep-sky observing.",
        "visibility": "Not visible",
    },
    {
        "emoji": "🌒", "name": "Waxing Crescent",
        "day_range": (1.84, 7.38),
        "desc": "A thin sliver of light grows on the right side (in the northern hemisphere). Sets a few hours after the Sun — early evenings are still dark.",
        "visibility": "Shortly after sunset",
    },
    {
        "emoji": "🌓", "name": "First Quarter",
        "day_range": (7.38, 9.22),
        "desc": "Half the Moon is lit. It rises around noon and sets around midnight — the second half of the night is still good for stargazing.",
        "visibility": "Afternoon to midnight",
    },
    {
        "emoji": "🌔", "name": "Waxing Gibbous",
        "day_range": (9.22, 14.77),
        "desc": "More than half illuminated and brightening. Moonlight begins to wash out fainter objects. Wait for it to set before pointing at nebulae.",
        "visibility": "Afternoon through early morning",
    },
    {
        "emoji": "🌕", "name": "Full Moon",
        "day_range": (14.77, 16.61),
        "desc": "Maximum brightness — the worst night for dark-sky observing. The Moon rises at sunset and is up all night. Great for lunar viewing though.",
        "visibility": "All night",
    },
    {
        "emoji": "🌖", "name": "Waning Gibbous",
        "day_range": (16.61, 22.15),
        "desc": "Still very bright but now rising after sunset. The first half of the night stays dark enough for serious observing before moonrise.",
        "visibility": "Midnight to mid-morning",
    },
    {
        "emoji": "🌗", "name": "Last Quarter",
        "day_range": (22.15, 23.99),
        "desc": "Half lit again, now on the left side. Rises around midnight — evenings are dark and usable until then.",
        "visibility": "Midnight to noon",
    },
    {
        "emoji": "🌘", "name": "Waning Crescent",
        "day_range": (23.99, 29.5),
        "desc": "A thinning sliver rises just before the Sun. Evenings and most of the night are beautifully dark — conditions nearly as good as New Moon.",
        "visibility": "Pre-dawn only",
    },
]


def moon_phase_page(request):
    from astral.moon import phase as _astral_phase
    from datetime import date

    p = _astral_phase(date.today())
    # Find index of current phase
    current_idx = 0
    for i, ph in enumerate(_MOON_PHASES):
        lo, hi = ph["day_range"]
        if lo <= p < hi:
            current_idx = i
            break

    # Reorder: current phase first, then the rest in cycle order
    ordered = _MOON_PHASES[current_idx:] + _MOON_PHASES[:current_idx]

    return render(request, "pages/moon_phase.html", {
        "phases": ordered,
        "current_name": _MOON_PHASES[current_idx]["name"],
        "cycle_day": round(p, 1),
    })


@login_required
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
        display_override = request.POST.get("display", "").strip()

        if lat and lon:
            # Browser geolocation, direct coords, or autocomplete selection
            try:
                lat, lon = float(lat), float(lon)
            except ValueError:
                return HttpResponse('<div class="alert error">Invalid coordinates.</div>')
            if display_override:
                # Photon already gave us a good label — skip reverse geocode
                display = display_override
            else:
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


@login_required
@require_http_methods(["GET", "POST"])
def preferences(request):
    if not request.user.is_authenticated:
        return redirect("home")

    prefs = request.prefs

    if request.method == "POST":
        try:
            display_name = request.POST.get("display_name", "").strip()
            if request.user.first_name != display_name:
                request.user.first_name = display_name
                request.user.save(update_fields=["first_name"])
            prefs.units = request.POST.get("units", "metric")
            tz = request.POST.get("timezone", "America/Chicago")
            if tz != prefs.timezone:
                prefs.timezone_auto = False
            prefs.timezone = tz
            prefs.min_score_threshold = int(request.POST.get("min_score_threshold", 40))
            prefs.disq_max_cloud_cover = int(request.POST.get("disq_max_cloud_cover", 85))
            prefs.disq_max_precip_prob = int(request.POST.get("disq_max_precip_prob", 40))
            prefs.disq_min_visibility_km = int(request.POST.get("disq_min_visibility_km", 10))
            bm = request.POST.get("best_metric", "combined")
            if bm in ("telescope", "naked_eye", "combined"):
                prefs.best_metric = bm
            prefs.save()
            return HttpResponse('<div class="alert success">Preferences saved.</div>')
        except Exception as e:
            return HttpResponse(f'<div class="alert error">Save failed: {e}</div>')

    tz_options = list(_COMMON_TIMEZONES)
    if prefs.timezone not in tz_options:
        tz_options.insert(0, prefs.timezone)

    return render(request, "pages/preferences.html", {
        "tz_options": tz_options,
    })


@login_required
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
    prefs.best_metric = "combined"
    # Re-detect timezone from location if available
    if prefs.has_location:
        tz = _tf.timezone_at(lat=prefs.location_lat, lng=prefs.location_lon)
        if tz:
            prefs.timezone = tz
            prefs.timezone_auto = True
    prefs.save()
    return redirect("preferences")


_KM_TO_MI = 0.621371

_STATE_ABBR = {
    # US states
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
    # Canadian provinces/territories
    "Alberta": "AB", "British Columbia": "BC", "Manitoba": "MB",
    "New Brunswick": "NB", "New Brunswick / Nouveau-Brunswick": "NB",
    "Newfoundland and Labrador": "NL", "Northwest Territories": "NT",
    "Nova Scotia": "NS", "Nunavut": "NU", "Ontario": "ON",
    "Prince Edward Island": "PE", "Québec": "QC", "Quebec": "QC",
    "Saskatchewan": "SK", "Yukon": "YT",
}

_SITE_TYPE_LABELS = {
    "ida_certified":   "IDA Certified",
    "state_park":      "State Park",
    "national_park":   "National Park",
    "national_forest": "National Forest",
    "observatory":     "Observatory",
    "community":       "Community",
    "user_submitted":  "User Submitted",
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
    type_filters    = request.GET.getlist("type")
    country_filters = request.GET.getlist("country")
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
    from accounts.models import Site, SiteDetail
    qs = Site.objects.filter(active=1)
    if type_filters:
        qs = qs.filter(site_type__in=type_filters)
    if country_filters:
        qs = qs.filter(country__in=country_filters)
    if bortle_max < 9:
        qs = qs.filter(bortle_class__lte=bortle_max)
    rows = list(qs.order_by("name").values(
        "id", "name", "lat", "lon", "bortle_class", "elevation_m",
        "notes", "site_type", "country", "state_province",
    ))

    # Which sites have enriched detail pages
    enriched_ids = set(SiteDetail.objects.values_list("site_id", flat=True))

    # ── Distance + display enrichment ─────────────────────────────────────────
    for row in rows:
        row["type_label"] = _SITE_TYPE_LABELS.get(row["site_type"] or "", row["site_type"] or "—")
        row["bortle_color"] = _BORTLE_COLOR.get(row["bortle_class"] or 5, "#555")
        row["state_abbr"] = _STATE_ABBR.get(row.get("state_province") or "", row.get("state_province") or "")
        code = (row.get("country") or "").upper()
        row["flag"] = (
            chr(0x1F1E6 + ord(code[0]) - 65) + chr(0x1F1E6 + ord(code[1]) - 65)
            if len(code) == 2 else ""
        )
        row["map_url"] = (
            f"https://www.openstreetmap.org/?mlat={row['lat']}&mlon={row['lon']}"
            f"#map=12/{row['lat']}/{row['lon']}"
        )
        row["has_detail"] = row["id"] in enriched_ids
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

    _COUNTRY_NAMES = {
        "US": "United States", "CA": "Canada", "MX": "Mexico",
        "GB": "United Kingdom", "AU": "Australia", "NZ": "New Zealand",
        "FR": "France", "DE": "Germany", "IT": "Italy", "ES": "Spain",
        "PT": "Portugal", "NO": "Norway", "SE": "Sweden", "FI": "Finland",
        "IS": "Iceland", "CH": "Switzerland", "AT": "Austria",
        "CZ": "Czech Republic", "PL": "Poland", "HU": "Hungary",
        "SK": "Slovakia", "HR": "Croatia", "SI": "Slovenia",
        "CL": "Chile", "AR": "Argentina", "BR": "Brazil", "PE": "Peru",
        "ZA": "South Africa", "NA": "Namibia", "KE": "Kenya",
        "JO": "Jordan", "IL": "Israel", "IN": "India", "JP": "Japan",
    }
    from django.db.models import Count
    country_qs = (
        Site.objects.filter(active=1)
        .exclude(country__isnull=True)
        .values("country")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    countries = [
        {
            "code": r["country"],
            "name": _COUNTRY_NAMES.get(r["country"], r["country"]),
            "flag": (
                chr(0x1F1E6 + ord(r["country"][0]) - 65) + chr(0x1F1E6 + ord(r["country"][1]) - 65)
                if len(r["country"]) == 2 else ""
            ),
            "count": r["count"],
        }
        for r in country_qs
    ]

    ctx = {
        "rows": page_rows,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "type_filters": type_filters,
        "country_filters": country_filters,
        "countries": countries,
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


@login_required
@require_http_methods(["GET"])
def site_detail(request, site_id):
    prefs = request.prefs
    is_imperial = prefs and prefs.units == "imperial"

    from django.http import Http404
    from accounts.models import Site
    try:
        obj = Site.objects.select_related("detail").get(id=site_id, active=1)
    except Site.DoesNotExist:
        raise Http404

    d = getattr(obj, "detail", None)
    site = {
        "id":                obj.id,
        "name":              obj.name,
        "lat":               obj.lat,
        "lon":               obj.lon,
        "bortle_class":      obj.bortle_class,
        "elevation_m":       obj.elevation_m,
        "notes":             obj.notes,
        "site_type":         obj.site_type,
        "country":           obj.country,
        "state_province":    obj.state_province,
        "wikipedia_url":     d.wikipedia_url     if d else None,
        "wikipedia_summary": d.wikipedia_summary if d else None,
        "image_url":         d.image_url         if d else None,
        "image_credit":      d.image_credit      if d else None,
        "narrative":         d.narrative         if d else None,
        "maps_url":          d.maps_url          if d else None,
        "enriched_at":       d.enriched_at       if d else None,
    }

    site["type_label"] = _SITE_TYPE_LABELS.get(site["site_type"] or "", site["site_type"] or "—")
    site["bortle_color"] = _BORTLE_COLOR.get(site["bortle_class"] or 5, "#555")
    site["state_abbr"] = _STATE_ABBR.get(site.get("state_province") or "", site.get("state_province") or "")
    code = (site.get("country") or "").upper()
    site["flag"] = (
        chr(0x1F1E6 + ord(code[0]) - 65) + chr(0x1F1E6 + ord(code[1]) - 65)
        if len(code) == 2 else ""
    )

    elev = site["elevation_m"]
    if elev is not None:
        if is_imperial:
            site["elevation_display"] = f"{elev * 3.28084:.0f} ft"
        else:
            site["elevation_display"] = f"{elev:.0f} m"
    else:
        site["elevation_display"] = None

    if prefs and prefs.has_location:
        km = _haversine(prefs.location_lat, prefs.location_lon, site["lat"], site["lon"])
        site["dist_display"] = f"{km * _KM_TO_MI:.0f} mi" if is_imperial else f"{km:.0f} km"
    else:
        site["dist_display"] = None

    # OSM map link as fallback if enrichment hasn't run yet
    if not site["maps_url"]:
        site["maps_url"] = (
            f"https://www.google.com/maps/search/?api=1&query={site['lat']},{site['lon']}"
        )

    came_from = request.GET.get("from", "sites")
    return render(request, "pages/site_detail.html", {"site": site, "came_from": came_from})


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

    from accounts.models import Site, SiteDailyScore
    if only_missing:
        scored_ids = set(
            SiteDailyScore.objects.filter(score_date=today, score__isnull=False)
            .values_list("site_id", flat=True)
        )
        sites = list(
            Site.objects.filter(active=1)
            .exclude(id__in=scored_ids)
            .values("id", "name", "lat", "lon", "bortle_class")
        )
    else:
        sites = list(Site.objects.filter(active=1).values("id", "name", "lat", "lon", "bortle_class"))

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
                from accounts.models import SiteDailyScore
                from django.utils import timezone as dj_tz
                now = dj_tz.now()
                SiteDailyScore.objects.bulk_create(
                    [
                        SiteDailyScore(
                            site_id=r["site_id"], score_date=r["date"],
                            name=r["name"], lat=r["lat"], lon=r["lon"],
                            score=r["score"], computed_at=now,
                        )
                        for r in batch
                    ],
                    update_conflicts=True,
                    unique_fields=["site_id", "score_date"],
                    update_fields=["score", "computed_at"],
                )
                batch = []
            if done % 50 == 0 or done == total:
                cache.set(_COMPUTE_STATE_KEY, {"running": True, "done": done, "total": total}, 600)

    cache.set(_COMPUTE_STATE_KEY, {"running": False, "done": done, "total": total}, 60)


def _today_local():
    return datetime.now(_CDT).date().isoformat()


def _load_heatmap_data(today):
    from accounts.models import SiteDailyScore
    qs = (
        SiteDailyScore.objects
        .filter(score_date=today)
        .order_by("-score")
        .values("name", "lat", "lon", "score", "computed_at")
    )
    rows = list(qs)
    if not rows:
        return None, None
    sites = []
    scored = 0
    computed_at = None
    for r in rows:
        sites.append({
            "name":  r["name"],
            "lat":   r["lat"],
            "lon":   r["lon"],
            "score": round(r["score"]) if r["score"] is not None else None,
            "color": _score_to_color(r["score"]),
        })
        if r["score"] is not None:
            scored += 1
        if computed_at is None and r["computed_at"] is not None:
            computed_at = r["computed_at"]
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

    top10 = []
    if sites:
        from accounts.models import SiteDailyScore
        top10 = [
            {
                "name":    r["name"],
                "score":   round(r["score"]),
                "bortle":  r["site__bortle_class"],
                "state":   r["site__state_province"],
                "country": r["site__country"],
                "color":   _score_to_color(r["score"]),
            }
            for r in (
                SiteDailyScore.objects
                .filter(score_date=today, score__isnull=False)
                .select_related("site")
                .order_by("-score")
                .values("name", "score", "site__bortle_class", "site__state_province", "site__country")[:10]
            )
        ]
        for i, site in enumerate(sites[:10]):
            site["rank"] = i + 1

    return render(request, "pages/heatmap.html", {
        "sites_json": json.dumps(sites or []),
        "meta": meta,
        "ts_str": ts_str,
        "today": today,
        "has_data": bool(sites),
        "is_admin": is_admin,
        "compute_state": compute_state,
        "missing_count": (meta["total"] - meta["scored"]) if meta else 0,
        "top10": top10,
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
    from accounts.models import AppSetting
    tz = AppSetting.get("timezone", "America/Chicago")

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


@require_http_methods(["GET"])
def sky_objects(request, site_id):
    """HTMX endpoint: return the _sky_objects.html partial for a site + date."""
    from datetime import date as date_type
    from engine.sky_objects import compute_sky
    from engine.cache import cache_get, cache_set

    from accounts.models import Site
    try:
        s = Site.objects.get(id=site_id, active=1)
    except Site.DoesNotExist:
        return HttpResponse('<p class="field-hint">Site not found.</p>', status=404)

    site_name, lat, lon, bortle = s.name, s.lat, s.lon, s.bortle_class or 5

    # Date: default to today, clamped to next 10 days
    today = date_type.today()
    raw_date = request.GET.get("date", today.isoformat())
    try:
        target_date = date_type.fromisoformat(raw_date)
    except ValueError:
        target_date = today
    max_date = today + timedelta(days=10)
    target_date = max(today, min(target_date, max_date))

    prefs = request.prefs if request.user.is_authenticated else _GuestPrefs()
    tz_name = getattr(prefs, "timezone", "America/Chicago")

    # Weather: pull cloud score from planner cache if available
    cloud_score = None
    try:
        from engine.cache import cache_get as cg
        forecast_cache_key = f"forecast:{site_id}:{target_date.isoformat()}"
        fc = cg(forecast_cache_key)
        if fc and "composite" in fc:
            cloud_score = int(fc["composite"])
    except Exception:
        pass

    cache_key = f"sky:{site_id}:{target_date.isoformat()}:{bortle}"
    result = cache_get(cache_key)
    if result is None:
        try:
            result = compute_sky(lat, lon, target_date, bortle, "large_scope", cloud_score, tz_name)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("sky_objects compute error: %s", e, exc_info=True)
            return HttpResponse('<p class="field-hint">Could not compute sky visibility. Please try again.</p>')
        cache_set(cache_key, result, 3600)

    date_options = [(today + timedelta(days=i)) for i in range(11)]
    return render(request, "pages/_sky_objects.html", {
        "sky":          result,
        "site_id":      site_id,
        "site_name":    site_name,
        "target_date":  target_date,
        "date_options": date_options,
    })


@require_http_methods(["GET"])
def tonight(request):
    """Standalone Tonight's Sky page (Spec 2)."""
    from datetime import date as date_type
    from engine.sky_objects import compute_sky, BORTLE_LIMITING_MAG
    from engine.cache import cache_get, cache_set

    prefs = request.prefs if request.user.is_authenticated else _GuestPrefs()
    has_location = prefs.has_location
    tz_name = getattr(prefs, "timezone", "America/Chicago")

    today = date_type.today()
    raw_date = request.GET.get("date", today.isoformat())
    try:
        target_date = date_type.fromisoformat(raw_date)
    except ValueError:
        target_date = today
    max_date = today + timedelta(days=10)
    target_date = max(today, min(target_date, max_date))

    sky = None
    bortle = None
    bortle_source = None
    forecast_scores = None

    if has_location:
        lat = prefs.location_lat
        lon = prefs.location_lon
        # Look up Bortle from World Atlas
        try:
            from engine.bortle_lookup import lookup_bortle
            result = lookup_bortle(lat, lon)
            bortle = (result.get("bortle") if isinstance(result, dict) else result) or 5
            bortle_source = "World Atlas of Artificial Sky Brightness"
        except Exception:
            bortle = 5
            bortle_source = "estimated"

        # Fetch planner-style forecast scores for the target date
        cloud_score = None
        try:
            from engine.forecast import fetch_site_forecast
            from engine.scorer import score_forecast
            fc_cache_key = f"sky:forecast:{lat:.4f}:{lon:.4f}:{target_date.isoformat()}"
            fc_data = cache_get(fc_cache_key)
            if fc_data is None:
                fc_data = fetch_site_forecast(
                    {"lat": lat, "lon": lon, "name": "Your location", "id": 0, "bortle_class": bortle},
                    forecast_days=11, timezone=tz_name,
                )
                cache_set(fc_cache_key, fc_data, 3600)
            nights = score_forecast(fc_data, tz_name)
            for n in nights:
                if n["date"] == target_date.isoformat():
                    forecast_scores = {
                        "composite":  round(n.get("composite") or 0),
                        "naked_eye":  round(n.get("naked_eye") or 0) if n.get("naked_eye") is not None else None,
                        "cloud_pct":  round(n.get("stats", {}).get("avg_cloud_cover") or 0),
                        "moon_score": round(n.get("factors", {}).get("moon") or 0),
                        "humidity":   round(n.get("stats", {}).get("avg_humidity") or 0),
                    }
                    cloud_score = forecast_scores["composite"]
                    break
        except Exception as e:
            _log.debug("Tonight forecast fetch failed: %s", e)

        cache_key = f"sky:tonight:{lat:.4f}:{lon:.4f}:{target_date.isoformat()}:{bortle}"
        sky = cache_get(cache_key)
        if sky is None:
            try:
                sky = compute_sky(lat, lon, target_date, bortle, "large_scope", cloud_score, tz_name)
                cache_set(cache_key, sky, 3600)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("tonight compute error: %s", e, exc_info=True)

    date_options = [(today + timedelta(days=i)) for i in range(11)]
    return render(request, "pages/tonight.html", {
        "sky":             sky,
        "has_location":    has_location,
        "location_name":   getattr(prefs, "location_display", "") or getattr(prefs, "location_text", ""),
        "bortle":          bortle,
        "bortle_source":   bortle_source,
        "forecast_scores": forecast_scores,
        "target_date":     target_date,
        "date_options":    date_options,
    })


@login_required
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


def _enrich_night(night, prefs, site_coords, site_ids=None, enriched_site_ids=None):
    stats = night.get("stats", {})
    factors = night.get("factors", {})
    lat, lon = site_coords.get(night["site"], (None, None))
    dist_str = ""
    dist_km = None
    if prefs and prefs.has_location and lat is not None:
        km = _haversine(prefs.location_lat, prefs.location_lon, lat, lon)
        dist_str = f"{km * _KM_TO_MI:.0f} mi" if prefs.units == "imperial" else f"{km:.0f} km"
        dist_km = km
    bortle = stats.get("bortle_class")
    metrics = [
        {"label": "Cloud Cover", "value": _fmt_val(stats.get("avg_cloud_cover"), suffix="%"),  "color": _metric_color(_norm(stats.get("avg_cloud_cover"),      0, 100, False)), "tip": "Average low/mid-level cloud cover during astronomical night. Lower is better — clouds are the #1 enemy of stargazing."},
        {"label": "High Cloud",  "value": _fmt_val(stats.get("avg_high_cloud"),  suffix="%"),  "color": _metric_color(_norm(stats.get("avg_high_cloud"),        0, 100, False)), "tip": "Thin cirrus cloud cover. Less obvious than low clouds but still reduces transparency and scatters light."},
        {"label": "Moon Score",  "value": _fmt_val(factors.get("moon")),                       "color": _metric_color(_norm(factors.get("moon"),                0, 100, True)),  "tip": "How moon-free the night is. 99 = new moon (ideal). Accounts for moon phase and hours above horizon."},
        {"label": "Night Hours", "value": _fmt_val(stats.get("night_hours"), ".0f", "h"),      "color": _metric_color(_norm(stats.get("night_hours"),           4,  12, True)),  "tip": "Hours of astronomical darkness (sun more than 18° below horizon). More hours = more time under truly dark skies."},
        {"label": "Humidity",    "value": _fmt_val(stats.get("avg_humidity"), suffix="%"),     "color": _metric_color(_norm(stats.get("avg_humidity"),          0, 100, False)), "tip": "Relative humidity. High humidity causes dew on optics and increases atmospheric haze, washing out faint objects."},
        {"label": "Stability",   "value": _fmt_val(factors.get("lifted_index")),               "color": _metric_color(_norm(factors.get("lifted_index"),        0, 100, True)),  "tip": "Atmospheric stability score derived from the lifted index. Higher = calmer air = steadier stars and sharper planetary views."},
        {"label": "Seeing †",    "value": _fmt_val(stats.get("seeing_7timer"), ".1f"),         "color": _metric_color(_norm(stats.get("seeing_7timer"),         1,   8, False)), "tip": "Atmospheric turbulence from 7timer (1–8, lower is better). Poor seeing makes stars twinkle and blur — critical for planets and double stars."},
        {"label": "Transp. †",   "value": _fmt_val(stats.get("transparency_7timer"), ".1f"),  "color": _metric_color(_norm(stats.get("transparency_7timer"),   1,   8, False)), "tip": "Atmospheric transparency from 7timer (1–8, lower is better). Affects how dark and clear the sky appears — key for deep-sky objects."},
        {"label": "Bortle",      "value": f"Class {bortle}" if bortle else "—",               "color": _metric_color(_norm(bortle,                             1,   9, False)), "tip": "Light pollution class (1–9, lower is better). Class 1 = pristine dark sky. Class 9 = inner-city sky. Determined by the World Atlas of Artificial Sky Brightness."},
    ]
    def _fmt_hour(iso_str):
        if not iso_str:
            return None
        h = datetime.fromisoformat(iso_str).hour
        if h == 0:
            return "12a"
        if h < 12:
            return f"{h}a"
        if h == 12:
            return "12p"
        return f"{h - 12}p"

    dark_start_str = stats.get("dark_start")
    dark_end_str   = stats.get("dark_end")
    dark_window = None
    if dark_start_str and dark_end_str:
        end_h = datetime.fromisoformat(dark_end_str).hour + 1  # last slot + 1hr = window end
        if end_h >= 24:
            end_label = "12a"
        else:
            end_label = _fmt_hour(dark_end_str[:11] + f"{end_h:02d}:00")
        dark_window = f"{_fmt_hour(dark_start_str)} – {end_label}"

    date_obj = datetime.fromisoformat(night["date"])
    composite = night.get("composite") or 0
    naked_eye = night.get("naked_eye")
    tel_norm = _norm(composite, 0, 100, True) or 0
    eye_norm = _norm(naked_eye, 0, 100, True) if naked_eye is not None else None
    map_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=12/{lat}/{lon}" if lat else ""
    has_7timer = stats.get("seeing_7timer") is not None or stats.get("transparency_7timer") is not None
    detail_metrics = [
        m for m in metrics
        if not (m["label"] in ("Seeing †", "Transp. †") and m["value"] == "—")
    ]
    return {
        **night,
        "date_str":         date_obj.strftime("%a %-d %b"),
        "date_day":         date_obj.strftime("%-d"),
        "date_month":       date_obj.strftime("%b").upper(),
        "dark_window":      dark_window,
        "dist_str":         dist_str,
        "dist_km":          dist_km,
        "metrics":          metrics,
        "summary_metrics":  [m for m in metrics if m["label"] != "Night Hours"],
        "detail_metrics":   detail_metrics,
        "has_7timer":       has_7timer,
        "tel_score":      round(composite),
        "eye_score":      round(naked_eye) if naked_eye is not None else None,
        "tel_color":      f"hsl({int(tel_norm * 120)}, 70%, 42%)",
        "eye_color":      f"hsl({int(eye_norm * 120)}, 70%, 42%)" if eye_norm is not None else "#555",
        "map_url":        map_url,
        "site_id":        site_ids.get(night["site"]) if site_ids else None,
        "has_detail":     (site_ids.get(night["site"]) in enriched_site_ids) if (site_ids and enriched_site_ids) else False,
    }


def _build_heatmap(nights, threshold, score_key="composite", dist_lookup=None, hm_sort="alpha"):
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
        info = dist_lookup.get(site) if dist_lookup else None
        rows.append({
            "site":     site,
            "cells":    cells,
            "dist_str": info["str"] if info else "",
            "dist_km":  info["km"]  if info else None,
        })
    if hm_sort == "dist" and dist_lookup:
        rows.sort(key=lambda r: r["dist_km"] if r["dist_km"] is not None else float("inf"))
    date_labels = [datetime.fromisoformat(d).strftime("%-d %b") for d in dates]
    return {"rows": rows, "dates": date_labels}


def _load_planner_sites(prefs, max_dist_km=None):
    from accounts.models import Site
    all_sites = list(Site.objects.filter(active=1).values("id", "name", "lat", "lon", "bortle_class", "site_type"))
    if prefs and prefs.has_location and max_dist_km:
        return [
            s for s in all_sites
            if _haversine(prefs.location_lat, prefs.location_lon, s["lat"], s["lon"]) <= max_dist_km
        ]
    return all_sites


def _run_planner_thread(prefix, sites, forecast_days, tz, disq):
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    state_key   = f"planner:status:{prefix}"
    results_key = f"planner:nights:{prefix}"
    total = len(sites)
    cache.set(state_key, {"running": True, "done": 0, "total": total}, 600)
    forecasts = []
    done = 0
    try:
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
    except Exception:
        logger.error("Planner thread crashed:\n%s", traceback.format_exc())
        cache.set(state_key, {"running": False, "done": done, "total": total, "error": True}, 120)


def _get_planner_max_sites():
    from accounts.models import AppSetting
    return int(AppSetting.get("planner_max_sites", 250))


@require_http_methods(["GET"])
def planner(request):
    prefs = request.prefs if request.user.is_authenticated else _GuestPrefs()
    is_guest = not request.user.is_authenticated

    try:
        radius_val = int(request.GET.get("radius", 300))
    except ValueError:
        radius_val = 300

    is_imperial = prefs.units == "imperial"
    dist_unit_str = "mi" if is_imperial else "km"
    radius_km = radius_val / _KM_TO_MI if is_imperial else radius_val

    # Ensure guest sessions have a session key
    if is_guest and not request.session.session_key:
        request.session.create()

    sites = _load_planner_sites(prefs, radius_km if prefs.has_location else None)
    max_sites = _get_planner_max_sites()
    site_count = len(sites)

    prefix = _planner_key_prefix(request)
    state_key   = f"planner:status:{prefix}"
    results_key = f"planner:nights:{prefix}"
    compute_state = cache.get(state_key)
    cached_nights_json = cache.get(results_key)

    _factor_labels = {
        "cloud_cover": "Cloud Cover", "high_cloud": "High Cloud",
        "moon": "Moon", "lifted_index": "Stability (LI)", "humidity": "Humidity",
    }
    from accounts.models import NakedEyeWeight, ScoringWeight
    tel_weights = list(ScoringWeight.objects.order_by("-weight").values_list("factor", "weight", "description"))
    eye_weights = list(NakedEyeWeight.objects.order_by("-weight").values_list("factor", "weight"))
    tel_rows = [{"factor": _factor_labels.get(r[0], r[0]), "weight": f"{r[1]*100:.0f}%", "notes": r[2]} for r in tel_weights]
    eye_desc  = {r[0]: r[2] for r in tel_weights}
    eye_rows  = [{"factor": _factor_labels.get(r[0], r[0]), "weight": f"{r[1]*100:.0f}%", "notes": eye_desc.get(r[0], "")} for r in eye_weights]

    return render(request, "pages/planner.html", {
        "prefs":           prefs,
        "is_guest":        is_guest,
        "site_count":      site_count,
        "effective_count": min(site_count, max_sites),
        "max_sites":       max_sites,
        "capped":          site_count > max_sites,
        "radius_val":      radius_val,
        "dist_unit":       dist_unit_str,
        "is_running":      bool(compute_state and compute_state.get("running")),
        "has_results":     bool(cached_nights_json),
        "compute_state":   compute_state,
        "tel_rows":        tel_rows,
        "eye_rows":        eye_rows,
    })


@require_http_methods(["GET"])
def planner_site_count(request):
    prefs = request.prefs if request.user.is_authenticated else _GuestPrefs()
    try:
        radius_val = int(request.GET.get("radius", 300))
    except ValueError:
        radius_val = 300

    is_imperial = prefs.units == "imperial"
    dist_unit = "mi" if is_imperial else "km"
    radius_km = radius_val / _KM_TO_MI if is_imperial else radius_val

    sites = _load_planner_sites(prefs, radius_km if prefs.has_location else None)
    max_sites = _get_planner_max_sites()
    site_count = len(sites)
    capped = site_count > max_sites
    effective_count = min(site_count, max_sites)

    return render(request, "pages/_site_count.html", {
        "site_count": site_count,
        "effective_count": effective_count,
        "max_sites": max_sites,
        "capped": capped,
        "radius_val": radius_val,
        "dist_unit": dist_unit,
        "has_location": bool(prefs.has_location),
    })


@require_http_methods(["POST"])
def planner_run(request):
    prefs = request.prefs if request.user.is_authenticated else _GuestPrefs()
    if not request.user.is_authenticated and not request.session.session_key:
        request.session.create()

    prefix = _planner_key_prefix(request)
    state_key = f"planner:status:{prefix}"
    state = cache.get(state_key)
    if state and state.get("running"):
        return render(request, "pages/_planner_progress.html", {"compute_state": state})

    is_imperial = prefs.units == "imperial"
    try:
        radius_val = int(request.POST.get("radius", 300))
    except ValueError:
        radius_val = 300
    radius_km = radius_val / _KM_TO_MI if is_imperial else radius_val

    sites = _load_planner_sites(prefs, radius_km if prefs.has_location else None)
    if not sites:
        return HttpResponse('<div class="alert error">No sites found in range. Try increasing your search radius.</div>')

    # Enforce site cap — sort closest-first so the user gets their nearest sites
    max_sites = _get_planner_max_sites()
    if len(sites) > max_sites:
        if prefs.has_location:
            sites.sort(key=lambda s: _haversine(prefs.location_lat, prefs.location_lon, s["lat"], s["lon"]))
        sites = sites[:max_sites]

    from accounts.models import AppSetting
    forecast_days = int(AppSetting.get("forecast_days", 10))

    tz = prefs.timezone
    disq = {
        "max_cloud_cover":   prefs.disq_max_cloud_cover,
        "max_precip_prob":   prefs.disq_max_precip_prob,
        "min_visibility_km": prefs.disq_min_visibility_km,
    }

    results_key = f"planner:nights:{prefix}"
    threading.Thread(
        target=_run_planner_thread,
        args=(prefix, sites, forecast_days, tz, disq),
        daemon=True,
    ).start()

    return render(request, "pages/_planner_progress.html", {
        "compute_state": {"running": True, "done": 0, "total": len(sites)},
    })


@require_http_methods(["GET"])
def planner_poll(request):
    prefix = _planner_key_prefix(request)
    state_key   = f"planner:status:{prefix}"
    results_key = f"planner:nights:{prefix}"
    state = cache.get(state_key) or {}

    if state.get("running"):
        return render(request, "pages/_planner_progress.html", {"compute_state": state})

    nights_json = cache.get(results_key)
    if not nights_json:
        return HttpResponse('<div class="alert warning">No results cached. Run the forecast first.</div>')

    return _render_results(request, json.loads(nights_json))


def _render_results(request, nights):
    from collections import defaultdict
    prefs = request.prefs
    threshold = prefs.min_score_threshold if prefs else 40
    best_metric = getattr(prefs, "best_metric", "combined")
    default_sort = "eye" if best_metric == "naked_eye" else "score"
    sort = request.GET.get("sort", default_sort)
    hm_sort = request.GET.get("hm_sort", "alpha")
    score_key = "naked_eye" if request.GET.get("view") == "eye" else "composite"
    today = datetime.now(ZoneInfo(prefs.timezone if prefs else "America/Chicago")).date()

    future = [n for n in nights if datetime.fromisoformat(n["date"]).date() >= today]

    scored_raw    = [n for n in future if not n.get("disqualified") and (n.get("composite") or 0) >= threshold]
    disq_raw      = [n for n in future if n.get("disqualified")]
    low_raw       = [n for n in future if not n.get("disqualified") and (n.get("composite") or 0) < threshold]

    # Enrich scored nights
    from accounts.models import Site, SiteDetail
    active_sites = Site.objects.filter(active=1).values("id", "name", "lat", "lon")
    site_coords  = {s["name"]: (s["lat"], s["lon"]) for s in active_sites}
    site_ids     = {s["name"]: s["id"]              for s in active_sites}
    enriched_site_ids = set(SiteDetail.objects.values_list("site_id", flat=True))

    enriched = [_enrich_night(n, prefs, site_coords, site_ids, enriched_site_ids) for n in scored_raw]

    # Minimally format non-scored nights (disqualified or below threshold)
    def _fmt_disq(n):
        date_obj = datetime.fromisoformat(n["date"])
        return {
            **n,
            "date_str":   date_obj.strftime("%a %-d %b"),
            "date_day":   date_obj.strftime("%-d"),
            "date_month": date_obj.strftime("%b").upper(),
        }
    disq_formatted = [_fmt_disq(n) for n in disq_raw]
    low_formatted  = [
        {**_fmt_disq(n), "below_threshold": True, "disqualified": f"Score {round(n.get('composite') or 0)} is below your minimum threshold of {threshold}"}
        for n in low_raw
    ]

    # Group by site
    scored_by_site = defaultdict(list)
    for n in enriched:
        scored_by_site[n["site"]].append(n)

    disq_by_site = defaultdict(list)
    for n in disq_formatted:
        disq_by_site[n["site"]].append(n)

    low_by_site = defaultdict(list)
    for n in low_formatted:
        low_by_site[n["site"]].append(n)

    def _score_color(score):
        norm = _norm(score, 0, 100, True) or 0
        return f"hsl({int(norm * 120)}, 70%, 42%)"

    # Build one record per site
    sites = []
    for site_name, site_nights in scored_by_site.items():
        tel_scores = [n["tel_score"] for n in site_nights]
        eye_scores = [n["eye_score"] for n in site_nights if n["eye_score"] is not None]

        if best_metric == "naked_eye":
            best_night = max(site_nights, key=lambda n: n["eye_score"] or 0)
        elif best_metric == "telescope":
            best_night = max(site_nights, key=lambda n: n["tel_score"])
        else:
            best_night = max(site_nights, key=lambda n: (
                (n["tel_score"] + n["eye_score"]) / 2 if n["eye_score"] is not None else n["tel_score"]
            ))

        # Merge scored + disq + below-threshold for this site, sorted by date (for date nav)
        all_nights = sorted(
            site_nights + disq_by_site.get(site_name, []) + low_by_site.get(site_name, []),
            key=lambda n: n["date"]
        )

        tel_min, tel_max = min(tel_scores), max(tel_scores)
        eye_min = min(eye_scores) if eye_scores else None
        eye_max = max(eye_scores) if eye_scores else None

        first = site_nights[0]
        sites.append({
            "name":          site_name,
            "site_id":       first.get("site_id"),
            "has_detail":    first.get("has_detail", False),
            "dist_str":      first.get("dist_str", ""),
            "dist_km":       first.get("dist_km"),
            "map_url":       first.get("map_url", ""),
            "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={site_coords[site_name][0]},{site_coords[site_name][1]}" if site_name in site_coords else "",
            "apple_maps_url":  f"https://maps.apple.com/?ll={site_coords[site_name][0]},{site_coords[site_name][1]}&z=12" if site_name in site_coords else "",
            "tel_min":       tel_min,
            "tel_max":       tel_max,
            "tel_min_color": _score_color(tel_min),
            "tel_max_color": _score_color(tel_max),
            "eye_min":       eye_min,
            "eye_max":       eye_max,
            "eye_min_color": _score_color(eye_min) if eye_min is not None else "#555",
            "eye_max_color": _score_color(eye_max) if eye_max is not None else "#555",
            "best_night":    best_night,
            "all_nights":    all_nights,
            "night_count":   len(site_nights),
        })

    # Sort sites
    if sort == "dist":
        sites.sort(key=lambda s: s["dist_km"] or 99999)
    elif sort == "eye":
        sites.sort(key=lambda s: -(s["eye_max"] or 0))
    else:  # score (default)
        sites.sort(key=lambda s: -s["tel_max"])

    # Sites with ALL nights disqualified (not in scored list)
    orphan_disq = [n for n in disq_formatted if n["site"] not in scored_by_site]

    # Distance lookup for heatmap
    is_imperial = prefs and prefs.units == "imperial"
    dist_lookup = {}
    if prefs and prefs.has_location:
        for site_name, (lat, lon) in site_coords.items():
            km = _haversine(prefs.location_lat, prefs.location_lon, lat, lon)
            dist_str = f"{km * _KM_TO_MI:.0f} mi" if is_imperial else f"{km:.0f} km"
            dist_lookup[site_name] = {"km": km, "str": dist_str}

    # Heatmap
    heatmap = _build_heatmap(future, threshold, score_key, dist_lookup=dist_lookup, hm_sort=hm_sort)

    # AI summary
    ai_summary = None
    try:
        if scored_raw and is_ollama_available():
            ai_summary = get_cached_summary(scored_raw[:10])
    except Exception:
        pass

    # Furthest result distance
    dist_kms = [s["dist_km"] for s in sites if s.get("dist_km")]
    max_dist_rounded = None
    if dist_kms:
        max_km = max(dist_kms)
        max_val = max_km * _KM_TO_MI if is_imperial else max_km
        max_dist_rounded = math.ceil(max_val / 10) * 10

    total_nights = sum(s["night_count"] for s in sites)
    total_disq   = len(disq_raw)

    return render(request, "pages/_planner_results.html", {
        "sites":         sites,
        "orphan_disq":   orphan_disq,
        "heatmap":       heatmap,
        "threshold":     threshold,
        "sort":          sort,
        "hm_sort":       hm_sort,
        "has_location":  bool(dist_lookup),
        "score_key":     score_key,
        "ai_summary":    ai_summary,
        "total_sites":   len(sites),
        "total_nights":  total_nights,
        "total_disq":    total_disq,
        "max_dist_rounded": max_dist_rounded,
        "best_metric":   best_metric,
    })


def admin_panel(request):
    from accounts.decorators import require_admin
    if not request.user.is_authenticated or not request.user.is_admin():
        return redirect("home")

    from accounts.models import AppSetting, NakedEyeWeight, Site, ScoringWeight
    tel_weights = list(ScoringWeight.objects.order_by("-weight").values("id", "factor", "weight", "description"))
    eye_weights = list(NakedEyeWeight.objects.order_by("-weight").values("id", "factor", "weight", "description"))
    bortle_null_count = Site.objects.filter(bortle_class__isnull=True).count()
    app_settings = list(AppSetting.objects.order_by("key").values("key", "value", "description"))

    from accounts.models import User as StarWolfUser
    users = (
        StarWolfUser.objects
        .prefetch_related("socialaccount_set")
        .order_by("date_joined")
    )

    from engine.ai_summary import _DEFAULT_SYSTEM_PROMPT, _DEFAULT_USER_PROMPT_TEMPLATE
    prompt_settings = dict(
        AppSetting.objects.filter(key__in=["ollama_system_prompt", "ollama_user_prompt"]).values_list("key", "value")
    )

    return render(request, "pages/admin.html", {
        "tel_weights": tel_weights,
        "eye_weights": eye_weights,
        "app_settings": app_settings,
        "bortle_null_count": bortle_null_count,
        "users": users,
        "ollama_system_prompt": prompt_settings.get("ollama_system_prompt", _DEFAULT_SYSTEM_PROMPT),
        "ollama_user_prompt": prompt_settings.get("ollama_user_prompt", _DEFAULT_USER_PROMPT_TEMPLATE),
        "default_system_prompt": _DEFAULT_SYSTEM_PROMPT,
        "default_user_prompt": _DEFAULT_USER_PROMPT_TEMPLATE,
    })


@require_http_methods(["POST"])
def admin_save_weights(request):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse('<div class="alert error">Admin only.</div>', status=403)

    from accounts.models import NakedEyeWeight, ScoringWeight
    table = request.POST.get("table", "scoring_weights")
    model = {"scoring_weights": ScoringWeight, "naked_eye_weights": NakedEyeWeight}.get(table)
    if not model:
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

    rows = [{"factor": f, "weight": w, "description": d}
            for f, w, d in zip(factors, weights, descriptions) if f.strip()]

    model.objects.all().delete()
    model.objects.bulk_create([model(**r) for r in rows])

    return HttpResponse('<div class="alert success">Weights saved.</div>')


@require_http_methods(["POST"])
def admin_save_settings(request):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse('<div class="alert error">Admin only.</div>', status=403)

    keys   = request.POST.getlist("key")
    values = request.POST.getlist("value")
    descs  = request.POST.getlist("description")

    from accounts.models import AppSetting
    for key, value, desc in zip(keys, values, descs):
        key = key.strip()
        if key:
            AppSetting.objects.update_or_create(key=key, defaults={"value": value, "description": desc})

    return HttpResponse('<div class="alert success">Settings saved.</div>')


@require_http_methods(["POST"])
def admin_bortle_fill(request):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse('<div class="alert error">Admin only.</div>', status=403)

    from accounts.models import Site
    null_sites = list(Site.objects.filter(bortle_class__isnull=True).order_by("name"))

    if not null_sites:
        return HttpResponse('<div class="alert success">No sites missing Bortle — nothing to do.</div>')

    ok, failed = 0, []
    for site in null_sites:
        try:
            result = lookup_bortle(site.lat, site.lon)
            site.bortle_class = result["bortle"]
            site.save(update_fields=["bortle_class"])
            ok += 1
        except Exception as e:
            failed.append(f"{site.name}: {e}")

    msg = f'<div class="alert success">Updated {ok} site(s).</div>'
    if failed:
        msg += '<div class="alert warning">Some failed:<br>' + "<br>".join(failed) + "</div>"
    return HttpResponse(msg)


@require_http_methods(["POST"])
def admin_save_prompts(request):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse('<div class="alert error">Admin only.</div>', status=403)

    system_prompt = request.POST.get("ollama_system_prompt", "").strip()
    user_prompt   = request.POST.get("ollama_user_prompt", "").strip()

    from accounts.models import AppSetting
    for key, value in [("ollama_system_prompt", system_prompt), ("ollama_user_prompt", user_prompt)]:
        AppSetting.objects.update_or_create(key=key, defaults={"value": value, "description": ""})

    # Bust the AI summary cache so next planner run picks up the new prompt
    from django.core.cache import cache
    cache.delete_pattern("ai_summary:*") if hasattr(cache, "delete_pattern") else None

    return HttpResponse('<div class="alert success">Prompts saved. Next planner run will use the updated prompt.</div>')


@require_http_methods(["POST"])
def admin_user_role(request, user_id):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse(status=403)
    from accounts.models import User as StarWolfUser
    target = get_object_or_404(StarWolfUser, id=user_id)
    if target == request.user:
        return HttpResponse('<span class="alert error">Cannot change your own role.</span>')
    new_role = request.POST.get("role")
    if new_role not in (StarWolfUser.GUEST, StarWolfUser.USER, StarWolfUser.ADMIN):
        return HttpResponse(status=400)
    target.role = new_role
    target.save(update_fields=["role"])
    return render(request, "pages/_admin_user_row.html", {"u": target, "current_user": request.user})


@require_http_methods(["POST"])
def admin_user_active(request, user_id):
    if not request.user.is_authenticated or not request.user.is_admin():
        return HttpResponse(status=403)
    from accounts.models import User as StarWolfUser
    target = get_object_or_404(StarWolfUser, id=user_id)
    if target == request.user:
        return HttpResponse('<span class="alert error">Cannot deactivate yourself.</span>')
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    return render(request, "pages/_admin_user_row.html", {"u": target, "current_user": request.user})


def api_guide(request):
    guide_path = Path(settings.BASE_DIR).parent / "docs" / "API_GUIDE.md"
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
