"""
Compute what's visible in the sky for a given location, date, and Bortle class.
Uses skyfield for ephemeris calculations and the sky_catalog DB table.
"""
import logging
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import requests

_log = logging.getLogger(__name__)

_EPHEMERIS_DIR = "/app/ephemeris"
_eph = None
_ts = None


def _get_eph():
    global _eph, _ts
    if _eph is None:
        from skyfield.api import Loader
        ldr = Loader(_EPHEMERIS_DIR)
        _ts = ldr.timescale()
        _eph = ldr("de421.bsp")
    return _eph, _ts


# ── Constants ────────────────────────────────────────────────────────────────

BORTLE_LIMITING_MAG = {
    1: 7.6, 2: 7.1, 3: 6.6, 4: 6.1,
    5: 5.6, 6: 5.1, 7: 4.5, 8: 4.0, 9: 3.0,
}

EQUIPMENT_GAIN = {
    "naked_eye":   0,
    "binoculars":  3,
    "small_scope": 5,
    "large_scope": 7,
}

# Fallback magnitudes when skyfield planetary_magnitude is unavailable
_PLANET_MEAN_MAG = {
    "Mercury": 0.2,
    "Venus":   -4.4,
    "Mars":    0.5,
    "Jupiter": -2.2,
    "Saturn":  0.7,
    "Uranus":  5.7,
    "Neptune": 7.8,
}

_MIN_ALTITUDE = 10.0
_ALT_EXTINCTION_THRESHOLD = 15.0

_COMPASS_16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]

def _az_compass(az_deg: float) -> str:
    return _COMPASS_16[round(az_deg / 22.5) % 16]


# ── Catalog helpers ───────────────────────────────────────────────────────────

def _load_catalog(category: str):
    """Return active SkyObject rows for the given category."""
    from accounts.models import SkyObject
    return list(SkyObject.objects.filter(category=category, active=True).order_by("sort_order", "name"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_time(t, tz: ZoneInfo) -> str:
    """Return time formatted as '9:14p' in the given timezone."""
    dt = t.utc_datetime().astimezone(tz)
    hour = dt.hour % 12 or 12
    suffix = "a" if dt.hour < 12 else "p"
    return f"{hour}:{dt.minute:02d}{suffix}"


def _next_shower(target_date: date) -> dict | None:
    """Return the next upcoming meteor shower peak after target_date (up to 365 days ahead)."""
    from accounts.models import SkyObject
    showers = list(SkyObject.objects.filter(category="meteor_shower", active=True))
    best = None
    for s in showers:
        ed = s.extra_data
        pm, pd = ed.get("peak_month"), ed.get("peak_day")
        if not pm or not pd:
            continue
        days = _days_to_peak(target_date, pm, pd)
        if days <= 0:
            continue
        if best is None or days < best["days"]:
            best = {"name": s.name, "days": days,
                    "peak_date": date(target_date.year if days <= 365 else target_date.year + 1, pm, pd),
                    "zhr": ed.get("zhr", 0)}
    return best


def _next_iss_pass(sat, lat: float, lon: float, target_date: date, ts, tz: ZoneInfo, days: int = 7) -> dict | None:
    """Search up to `days` ahead for the next ISS pass; return first result or None."""
    from skyfield.api import wgs84
    observer = wgs84.latlon(lat, lon)
    for offset in range(1, days + 1):
        d = target_date + timedelta(days=offset)
        t0 = ts.utc(d.year, d.month, d.day, 0)
        t1 = ts.utc(d.year, d.month, d.day, 23, 59)
        try:
            times, events = sat.find_events(observer, t0, t1, altitude_degrees=10.0)
        except Exception:
            continue
        current = {}
        for t, e in zip(times, events):
            e = int(e)
            t = ts.tt_jd(float(t.tt))
            if e == 0:
                current = {"rise": t}
            elif e == 1 and current:
                diff = sat - observer
                alt, az, _ = diff.at(t).altaz()
                current["peak_alt"] = round(alt.degrees)
            elif e == 2 and "rise" in current:
                rise_t = current["rise"]
                duration_s = (float(t.tt) - float(rise_t.tt)) * 86400
                return {
                    "rise_str":   _fmt_time(rise_t, tz),
                    "duration_m": max(1, round(duration_s / 60)),
                    "peak_alt":   current.get("peak_alt", 0),
                    "days_ahead": offset,
                }
    return None


def _days_to_peak(target_date: date, peak_month: int, peak_day: int) -> int:
    """Return signed days from target_date to the shower peak in the same year (or next)."""
    peak = date(target_date.year, peak_month, peak_day)
    delta = (peak - target_date).days
    if delta < -180:
        peak = date(target_date.year + 1, peak_month, peak_day)
        delta = (peak - target_date).days
    if delta > 180:
        peak = date(target_date.year - 1, peak_month, peak_day)
        delta = (peak - target_date).days
    return delta


def _visibility_tier(magnitude: float, effective_limit: float) -> tuple[int, str, str]:
    """Return (tier, label, emoji) based on magnitude vs site+equipment limit."""
    bortle_limit = effective_limit - EQUIPMENT_GAIN["large_scope"]
    if magnitude <= bortle_limit:
        return 0, "Naked Eye", "🟢"
    if magnitude <= bortle_limit + EQUIPMENT_GAIN["binoculars"]:
        return 1, "Binoculars", "🔵"
    if magnitude <= bortle_limit + EQUIPMENT_GAIN["small_scope"]:
        return 2, "Small Scope", "🔭"
    if magnitude <= effective_limit:
        return 3, "Large Scope", "🔭🔭"
    return 4, "Not Tonight", "⛔"


def _effective_limit(bortle: int, equipment: str) -> float:
    """Compute the faintest magnitude detectable given Bortle and equipment."""
    base = BORTLE_LIMITING_MAG.get(bortle, 5.6)
    gain = EQUIPMENT_GAIN.get(equipment, EQUIPMENT_GAIN["large_scope"])
    return base + gain


def _altaz_series(observer, obj, t_start, t_end, ts, n: int = 72):
    """Return (times_array, alt_degrees_array, az_degrees_array) across the night window."""
    jd = np.linspace(t_start.whole + t_start.tt_fraction, t_end.whole + t_end.tt_fraction, n)
    times = ts.tt_jd(jd)
    astrometric = observer.at(times).observe(obj)
    alts, azs, _ = astrometric.apparent().altaz()
    return times, alts.degrees, azs.degrees


def _night_window(eph, ts, observer, target_date: date):
    """Return (t_start, t_end) covering astronomical night for the date."""
    from skyfield import almanac
    t0 = ts.utc(target_date.year, target_date.month, target_date.day, 12)
    next_day = target_date + timedelta(days=1)
    t1 = ts.utc(next_day.year, next_day.month, next_day.day, 12)

    try:
        f = almanac.dark_twilight_day(eph, observer)
        times, events = almanac.find_discrete(t0, t1, f)
        night_start = night_end = None
        for t, e in zip(times, events):
            t_sc = ts.tt_jd(float(t.tt))
            if int(e) == 0 and night_start is None:
                night_start = t_sc
            elif int(e) != 0 and night_start is not None and night_end is None:
                night_end = t_sc
                break
    except Exception:
        night_start = night_end = None

    if night_start is None:
        night_start = ts.utc(target_date.year, target_date.month, target_date.day, 1)
    if night_end is None:
        night_end = ts.utc(next_day.year, next_day.month, next_day.day, 11)
    return night_start, night_end


def _rise_set(eph, obj, observer, t0, t1):
    """Return (rise_t, set_t) within [t0, t1], either may be None."""
    from skyfield import almanac
    try:
        f = almanac.risings_and_settings(eph, obj, observer)
        times, events = almanac.find_discrete(t0, t1, f)
        rise = set_ = None
        for t, e in zip(times, events):
            t_sc = t.ts.tt_jd(float(t.tt))
            if int(e) == 1 and rise is None:
                rise = t_sc
            elif int(e) == 0 and set_ is None:
                set_ = t_sc
        return rise, set_
    except Exception:
        return None, None


# ── ISS / Satellite passes ────────────────────────────────────────────────────

def _fetch_tle(tle_url: str, cache_key: str) -> tuple[str, str] | None:
    """Fetch TLE lines from Celestrak. Returns (line1, line2) or None. Cached 6h."""
    from django.core.cache import cache
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        resp = requests.get(tle_url, timeout=5)
        resp.raise_for_status()
        lines = [l.strip() for l in resp.text.strip().splitlines() if l.strip()]
        if len(lines) >= 3:
            result = (lines[1], lines[2])
        elif len(lines) == 2:
            result = (lines[0], lines[1])
        else:
            return None
        cache.set(cache_key, result, 6 * 3600)
        return result
    except Exception as e:
        _log.debug("TLE fetch failed (%s): %s", tle_url, e)
        return None


def _compute_satellite_passes(sat_obj, lat: float, lon: float, t0, t1, ts, tz: ZoneInfo) -> list[dict]:
    """Return list of pass dicts for a satellite during the night window."""
    from skyfield.api import wgs84
    try:
        observer = wgs84.latlon(lat, lon)
        times, events = sat_obj.find_events(observer, t0, t1, altitude_degrees=10.0)
        passes = []
        current = {}
        for t, e in zip(times, events):
            e = int(e)
            t = ts.tt_jd(float(t.tt))
            if e == 0:
                current = {"rise": t}
            elif e == 1 and current:
                diff = sat_obj - observer
                topocentric = diff.at(t)
                alt, az, _ = topocentric.altaz()
                current["peak"] = t
                current["peak_alt"] = round(alt.degrees)
                current["peak_az"] = az.degrees
            elif e == 2 and "rise" in current:
                current["set"] = t
                rise_t, set_t = current["rise"], current["set"]
                duration_s = (float(set_t.tt) - float(rise_t.tt)) * 86400
                az_deg = current.get("peak_az", 0)
                directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                direction = directions[round(az_deg / 45) % 8]
                passes.append({
                    "rise_str":   _fmt_time(rise_t, tz),
                    "peak_str":   _fmt_time(current["peak"], tz) if "peak" in current else "—",
                    "set_str":    _fmt_time(set_t, tz),
                    "duration_m": max(1, round(duration_s / 60)),
                    "peak_alt":   current.get("peak_alt", 0),
                    "direction":  direction,
                })
                current = {}
        return passes
    except Exception as e:
        import traceback
        _log.debug("Satellite pass computation failed: %s\n%s", e, traceback.format_exc())
        return []


# ── Main computation ──────────────────────────────────────────────────────────

def compute_sky(
    lat: float,
    lon: float,
    target_date: date,
    bortle: int,
    equipment: str = "large_scope",
    cloud_score: int | None = None,
    tz_name: str = "America/Chicago",
) -> dict:
    """
    Compute everything visible in the sky for the given location and date.
    Returns a structured dict consumed by the _sky_objects.html template.
    """
    from skyfield.api import EarthSatellite, Star, wgs84
    eph, ts = _get_eph()

    tz = ZoneInfo(tz_name)
    observer = eph["earth"] + wgs84.latlon(lat, lon)
    earth = eph["earth"]

    t_start, t_end = _night_window(eph, ts, wgs84.latlon(lat, lon), target_date)
    eff_limit = _effective_limit(bortle, equipment)
    limiting_mag = BORTLE_LIMITING_MAG.get(bortle, 5.6)

    # ── Moon ─────────────────────────────────────────────────────────────────
    moon_obj = eph["moon"]
    moon_times, moon_alts, _ = _altaz_series(observer, moon_obj, t_start, t_end, ts)
    moon_peak_idx = int(np.argmax(moon_alts))
    moon_peak_alt = round(float(moon_alts[moon_peak_idx]))
    moon_peak_t = moon_times[moon_peak_idx]

    moon_rise, moon_set = _rise_set(eph, moon_obj, observer, t_start, t_end)

    t_mid = ts.tt_jd(((t_start.whole + t_start.tt_fraction) + (t_end.whole + t_end.tt_fraction)) / 2)
    sun_obj = eph["sun"]
    e = earth.at(t_mid)
    s = e.observe(sun_obj).apparent()
    m = e.observe(moon_obj).apparent()
    _, slon, _ = s.ecliptic_latlon()
    _, mlon, _ = m.ecliptic_latlon()
    phase_angle = (mlon.degrees - slon.degrees) % 360
    illumination = round(50 * (1 - math.cos(math.radians(phase_angle))))

    if phase_angle < 45:
        phase_name = "New Moon" if phase_angle < 10 else "Waxing Crescent"
    elif phase_angle < 135:
        phase_name = "First Quarter" if 80 < phase_angle < 100 else "Waxing Gibbous"
    elif phase_angle < 225:
        phase_name = "Full Moon" if 170 < phase_angle < 190 else "Waning Gibbous"
    elif phase_angle < 315:
        phase_name = "Last Quarter" if 260 < phase_angle < 280 else "Waning Crescent"
    else:
        phase_name = "Waxing Crescent"

    moon = {
        "phase_name":   phase_name,
        "illumination": illumination,
        "peak_alt":     moon_peak_alt,
        "peak_str":     _fmt_time(moon_peak_t, tz),
        "rise_str":     _fmt_time(moon_rise, tz) if moon_rise else None,
        "set_str":      _fmt_time(moon_set, tz) if moon_set else None,
        "above_horizon": moon_peak_alt > 0,
        "bright":       illumination > 40,
    }

    # ── Planets ──────────────────────────────────────────────────────────────
    planets = []
    for planet in _load_catalog("planet"):
        body_key = planet.extra_data.get("ephemeris_name", planet.name.lower())
        try:
            planet_obj = eph[body_key]
        except Exception:
            continue

        times, alts, azs = _altaz_series(observer, planet_obj, t_start, t_end, ts)
        peak_idx = int(np.argmax(alts))
        peak_alt = float(alts[peak_idx])
        peak_t = times[peak_idx]

        above = alts > _MIN_ALTITUDE
        if not np.any(above):
            planets.append({"name": planet.name, "visible": False, "note": "Below horizon tonight"})
            continue

        p_rise, p_set = _rise_set(eph, planet_obj, observer, t_start, t_end)

        try:
            from skyfield.magnitudes import planetary_magnitude
            astr = observer.at(times[peak_idx]).observe(planet_obj)
            mag = round(planetary_magnitude(astr.apparent()), 1)
        except Exception:
            mag = _PLANET_MEAN_MAG.get(planet.name, 5.0)

        eff_mag = mag + (1.0 if peak_alt < _ALT_EXTINCTION_THRESHOLD else 0.0)
        tier, tier_label, tier_emoji = _visibility_tier(eff_mag, eff_limit)

        planets.append({
            "name":       planet.name,
            "visible":    True,
            "magnitude":  mag,
            "peak_alt":   round(peak_alt),
            "peak_az":    _az_compass(float(azs[peak_idx])),
            "peak_str":   _fmt_time(peak_t, tz),
            "rise_str":   _fmt_time(p_rise, tz) if p_rise else None,
            "set_str":    _fmt_time(p_set, tz) if p_set else None,
            "tier":       tier,
            "tier_label": tier_label,
            "tier_emoji": tier_emoji,
            "reachable":  tier < 4,
        })

    planets.sort(key=lambda p: (not p["visible"], p.get("tier", 4), -p.get("peak_alt", 0)))

    # ── Stars ─────────────────────────────────────────────────────────────────
    stars = []
    for star_obj in _load_catalog("star"):
        star = Star(ra_hours=star_obj.ra_h, dec_degrees=star_obj.dec_d)
        times, alts, azs = _altaz_series(observer, star, t_start, t_end, ts)
        above = alts > _MIN_ALTITUDE
        if not np.any(above):
            continue

        peak_idx = int(np.argmax(alts))
        peak_alt = float(alts[peak_idx])
        peak_t = times[peak_idx]
        above_idx = np.where(above)[0]
        vis_start_t = times[int(above_idx[0])]
        vis_end_t   = times[int(above_idx[-1])]

        mag = star_obj.magnitude
        eff_mag = mag + (1.0 if peak_alt < _ALT_EXTINCTION_THRESHOLD else 0.0)
        tier, tier_label, tier_emoji = _visibility_tier(eff_mag, eff_limit)

        if tier >= 4:
            continue

        stars.append({
            "name":        star_obj.name,
            "common_name": star_obj.common_name,
            "obj_type":    star_obj.obj_type,
            "magnitude":   mag,
            "peak_alt":    round(peak_alt),
            "peak_az":     _az_compass(float(azs[peak_idx])),
            "peak_str":    _fmt_time(peak_t, tz),
            "vis_start":   _fmt_time(vis_start_t, tz),
            "vis_end":     _fmt_time(vis_end_t, tz),
            "tier":        tier,
            "tier_label":  tier_label,
            "tier_emoji":  tier_emoji,
            "notes":       star_obj.notes,
        })

    stars.sort(key=lambda s: (s["tier"], s["magnitude"]))

    # ── DSOs ─────────────────────────────────────────────────────────────────
    dsos = []
    dsos_drive = []
    for dso in _load_catalog("dso"):
        if dso.ra_h is None or dso.dec_d is None or dso.magnitude is None:
            continue
        star = Star(ra_hours=dso.ra_h, dec_degrees=dso.dec_d)
        times, alts, azs = _altaz_series(observer, star, t_start, t_end, ts)
        above = alts > _MIN_ALTITUDE
        if not np.any(above):
            continue

        peak_idx = int(np.argmax(alts))
        peak_alt = float(alts[peak_idx])
        peak_t = times[peak_idx]
        above_idx = np.where(above)[0]
        vis_start_t = times[int(above_idx[0])]
        vis_end_t   = times[int(above_idx[-1])]

        mag = dso.magnitude
        eff_mag = mag + (1.0 if peak_alt < _ALT_EXTINCTION_THRESHOLD else 0.0)
        tier, tier_label, tier_emoji = _visibility_tier(eff_mag, eff_limit)

        entry = {
            "name":        dso.name,
            "common_name": dso.common_name,
            "obj_type":    dso.obj_type,
            "magnitude":   mag,
            "peak_alt":    round(peak_alt),
            "peak_az":     _az_compass(float(azs[peak_idx])),
            "peak_str":    _fmt_time(peak_t, tz),
            "vis_start":   _fmt_time(vis_start_t, tz),
            "vis_end":     _fmt_time(vis_end_t, tz),
            "tier":        tier,
            "tier_label":  tier_label,
            "tier_emoji":  tier_emoji,
        }

        if tier < 4:
            dsos.append(entry)
        elif mag <= limiting_mag + EQUIPMENT_GAIN["large_scope"]:
            dark_limit = BORTLE_LIMITING_MAG[3] + EQUIPMENT_GAIN["large_scope"]
            if mag <= dark_limit:
                dsos_drive.append(entry)

    dsos.sort(key=lambda d: (d["tier"], -d["peak_alt"]))
    dsos_drive.sort(key=lambda d: (-d["peak_alt"], d["magnitude"]))

    # ── Meteor Showers ────────────────────────────────────────────────────────
    showers = []
    for shower in _load_catalog("meteor_shower"):
        ed = shower.extra_data
        peak_month = ed.get("peak_month")
        peak_day   = ed.get("peak_day")
        zhr        = ed.get("zhr", 0)
        ra_h       = ed.get("radiant_ra_h")
        dec_d      = ed.get("radiant_dec_d")
        if not all([peak_month, peak_day, ra_h is not None, dec_d is not None]):
            continue

        days = _days_to_peak(target_date, peak_month, peak_day)
        if abs(days) > 14:
            continue

        radiant = Star(ra_hours=ra_h, dec_degrees=dec_d)
        _, rad_alts, _ = _altaz_series(observer, radiant, t_start, t_end, ts)
        max_rad_alt = float(np.max(rad_alts))

        if days < 0:
            timing = f"peaked {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
            active = abs(days) <= 3
        elif days == 0:
            timing = "peak tonight"
            active = True
        else:
            timing = f"peaks in {days} day{'s' if days != 1 else ''}"
            active = days <= 3

        showers.append({
            "name":        shower.name,
            "zhr":         zhr,
            "timing":      timing,
            "active":      active,
            "days":        days,
            "radiant_alt": round(max_rad_alt),
            "radiant_up":  max_rad_alt > _MIN_ALTITUDE,
        })

    showers.sort(key=lambda s: abs(s["days"]))

    # ── Satellites ────────────────────────────────────────────────────────────
    all_passes = []
    iss_sat = None
    for sat_row in _load_catalog("satellite"):
        ed = sat_row.extra_data
        tle_url  = ed.get("tle_source_url")
        norad_id = ed.get("norad_id")
        if not tle_url:
            continue
        cache_key = f"tle:{norad_id or sat_row.name}"
        tle = _fetch_tle(tle_url, cache_key)
        if not tle:
            continue
        sat = EarthSatellite(tle[0], tle[1], sat_row.name, ts)
        if sat_row.name == "ISS":
            iss_sat = sat
        passes = _compute_satellite_passes(sat, lat, lon, t_start, t_end, ts, tz)
        all_passes.extend(passes)

    all_passes.sort(key=lambda p: p["rise_str"])

    next_iss  = _next_iss_pass(iss_sat, lat, lon, target_date, ts, tz) if iss_sat and not all_passes else None
    next_shower = _next_shower(target_date) if not showers else None

    # ── Weather note ─────────────────────────────────────────────────────────
    weather_note = None
    if cloud_score is not None:
        if cloud_score >= 70:
            weather_note = {"level": "good",     "text": "Clear skies expected — excellent conditions for the above."}
        elif cloud_score >= 40:
            weather_note = {"level": "marginal",  "text": "Partly cloudy forecast — some objects may be obscured. Check the Planner for a clearer night."}
        else:
            weather_note = {"level": "poor",      "text": "Significant cloud cover expected. Visibility tiers assume clear skies."}

    return {
        "moon":         moon,
        "planets":      planets,
        "stars":        stars,
        "dsos":         dsos,
        "dsos_drive":   dsos_drive,
        "showers":      showers,
        "next_shower":  next_shower,
        "iss_passes":   all_passes,
        "next_iss":     next_iss,
        "weather_note": weather_note,
        "bortle":       bortle,
        "limiting_mag": limiting_mag,
        "eff_limit":    eff_limit,
        "equipment":    equipment,
        "night_start":  _fmt_time(t_start, tz),
        "night_end":    _fmt_time(t_end, tz),
    }
