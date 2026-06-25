import math
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.moon import phase as moon_phase, moonrise
from astral.sun import night as astral_night

from sqlalchemy import text
from db import get_engine


# ── per-factor scorers (each returns 0–100) ────────────────────────────────────

def _score_cloud_cover(pct: float) -> float:
    return max(0.0, 100.0 - pct)


def _score_high_cloud(pct: float) -> float:
    return max(0.0, 100.0 - pct)


def _score_lifted_index(li: float) -> float:
    # Map [-10, +5] → [0, 100]; values outside that range are clamped
    return max(0.0, min(100.0, (li + 10.0) / 15.0 * 100.0))


def _score_humidity(rh: float) -> float:
    # Full score below 60 RH; linear penalty up to 100 RH
    return max(0.0, min(100.0, (100.0 - rh) / 40.0 * 100.0))


def _bortle_naked_eye_modifier(bortle_class: int | None) -> float:
    """
    Returns a multiplier (0.7–1.0) applied to the naked eye composite.
    Bortle 1–2 → no penalty; Bortle 3–4 → mild; Bortle 5–6 → moderate; Bortle 7+ → heavy.
    Returns 1.0 if bortle_class is None (unknown site).
    """
    if bortle_class is None:
        return 1.0
    modifiers = {1: 1.0, 2: 1.0, 3: 0.92, 4: 0.84, 5: 0.75, 6: 0.70, 7: 0.65, 8: 0.60, 9: 0.55}
    return modifiers.get(bortle_class, 1.0)


def _score_moon(obs_date: date, lat: float, lon: float, tz_str: str) -> float:
    """0–100, higher = better (low illumination + sets before dark ends)."""
    loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz_str)
    tz = ZoneInfo(tz_str)

    p = moon_phase(obs_date)
    illum = (1 - abs(p - 14) / 14) * 100  # 0 = new moon, 100 = full moon

    try:
        dark_start, dark_end = astral_night(loc.observer, date=obs_date, tzinfo=tz)
        try:
            mr = moonrise(loc.observer, date=obs_date, tzinfo=tz)
            if mr is None or mr >= dark_end:
                dark_hrs = (dark_end - dark_start).seconds / 3600
            elif mr <= dark_start:
                dark_hrs = 0.0
            else:
                dark_hrs = (mr - dark_start).seconds / 3600
        except Exception:
            dark_hrs = (dark_end - dark_start).seconds / 3600
    except Exception:
        dark_hrs = 9.0  # fallback: assume full dark window

    moon_penalty = (illum / 100) * (1 - dark_hrs / 9)
    return round(max(0.0, min(100.0, (1 - moon_penalty) * 100)), 1)




# ── helpers ────────────────────────────────────────────────────────────────────

def _night_key(timestamp_str: str) -> date:
    """Assign a nighttime hour to its observing night (evening date).
    Hours after midnight belong to the previous calendar date's night.
    """
    dt = datetime.fromisoformat(timestamp_str)
    return (dt - timedelta(days=1)).date() if dt.hour < 12 else dt.date()


def _7timer_by_night(seven_timer_data: dict, tz_str: str) -> dict:
    """Return {night_date: [slots]} from a 7timer response."""
    if not seven_timer_data:
        return {}

    tz = ZoneInfo(tz_str)
    init_str = seven_timer_data.get("init", "")
    try:
        init_dt = datetime.strptime(init_str, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    except ValueError:
        return {}

    by_night = {}
    for slot in seven_timer_data.get("dataseries", []):
        slot_local = (init_dt + timedelta(hours=slot["timepoint"])).astimezone(tz)
        nk = _night_key(slot_local.strftime("%Y-%m-%dT%H:%M"))
        by_night.setdefault(nk, []).append(slot)

    return by_night


def _load_weights() -> dict:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT factor, weight FROM scoring_weights")).fetchall()
    return dict(rows)


def _load_naked_eye_weights() -> dict:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT factor, weight FROM naked_eye_weights")).fetchall()
    return dict(rows)


def _avg(values: list) -> float | None:
    clean = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return sum(clean) / len(clean) if clean else None


def _seven_timer_tier(seeing_avg: float | None, trans_avg: float | None) -> dict:
    if seeing_avg is None or trans_avg is None:
        return {"tier": "no_data", "score": None, "seeing": seeing_avg, "transparency": trans_avg}
    seeing_score = (8 - seeing_avg) / 7 * 100
    trans_score  = (8 - trans_avg)  / 7 * 100
    blended = round(0.65 * seeing_score + 0.35 * trans_score, 1)
    if blended >= 70:
        tier = "excellent"
    elif blended >= 40:
        tier = "good"
    else:
        tier = "mediocre"
    return {"tier": tier, "score": blended, "seeing": seeing_avg, "transparency": trans_avg}


# ── public API ─────────────────────────────────────────────────────────────────

def score_forecast(forecast: dict, tz_str: str, disqualifiers: dict | None = None) -> list:
    """Score every night in a single site's forecast.

    Returns a list of dicts (one per night):
      site      — site name
      date      — ISO date string of the observing evening
      composite — weighted 0–100 score
      factors   — per-factor 0–100 scores
      stats     — raw averages and 7timer supplemental data
    """
    site = forecast["site"]
    om = forecast["open_meteo"]

    if not om:
        return []

    weights = _load_weights()
    naked_eye_weights = _load_naked_eye_weights()

    hourly = om["hourly"]
    times = hourly["time"]
    is_day = hourly["is_day"]

    # Group nighttime hour indices by observing night
    nights: dict[date, list[int]] = {}
    for i, (t, d) in enumerate(zip(times, is_day)):
        if d == 0:
            nights.setdefault(_night_key(t), []).append(i)

    st7_nights = _7timer_by_night(forecast.get("seven_timer"), tz_str)

    results = []
    for night_date, idxs in sorted(nights.items()):
        def field_avg(key):
            return _avg([hourly[key][i] for i in idxs])

        avg_cloud      = field_avg("cloud_cover")
        avg_hi_cloud   = field_avg("cloud_cover_high")
        avg_li         = field_avg("lifted_index")
        avg_rh         = field_avg("relative_humidity_2m")
        avg_precip     = field_avg("precipitation_probability")
        avg_vis_km     = (_avg([hourly["visibility"][i] for i in idxs]) or 0) / 1000

        disq_reasons = []
        if disqualifiers:
            if avg_cloud  is not None and avg_cloud  > disqualifiers.get("max_cloud_cover",    100):
                disq_reasons.append(f"Cloud cover {avg_cloud:.0f}% > {disqualifiers['max_cloud_cover']}% limit")
            if avg_precip is not None and avg_precip > disqualifiers.get("max_precip_prob",    100):
                disq_reasons.append(f"Precip. prob. {avg_precip:.0f}% > {disqualifiers['max_precip_prob']}% limit")
            if avg_vis_km < disqualifiers.get("min_visibility_km", 0):
                disq_reasons.append(f"Visibility {avg_vis_km:.1f} km < {disqualifiers['min_visibility_km']} km minimum")

        factor_scores = {
            "cloud_cover":  _score_cloud_cover(avg_cloud or 0),
            "high_cloud":   _score_high_cloud(avg_hi_cloud or 0),
            "moon":         _score_moon(night_date, site["lat"], site["lon"], tz_str),
            "lifted_index": _score_lifted_index(avg_li if avg_li is not None else 0),
            "humidity":     _score_humidity(avg_rh if avg_rh is not None else 50),
        }

        bortle = site.get("bortle_class")

        composite = sum(
            factor_scores.get(factor, 50.0) * weight
            for factor, weight in weights.items()
        )

        naked_eye_composite = sum(
            factor_scores.get(factor, 50.0) * weight
            for factor, weight in naked_eye_weights.items()
        ) * _bortle_naked_eye_modifier(bortle)

        # 7timer supplemental seeing + transparency (not in composite score)
        st7_slots = st7_nights.get(night_date, [])
        st7_seeing = [s["seeing"] for s in st7_slots if "seeing" in s]
        st7_trans  = [s["transparency"] for s in st7_slots if "transparency" in s]

        avg_st7_seeing = round(sum(st7_seeing) / len(st7_seeing), 1) if st7_seeing else None
        avg_st7_trans  = round(sum(st7_trans)  / len(st7_trans),  1) if st7_trans  else None

        entry = {
            "site":             site["name"],
            "date":             night_date.isoformat(),
            "composite":        round(composite, 1),
            "naked_eye":        round(naked_eye_composite, 1),
            "factors":          {k: round(v, 1) for k, v in factor_scores.items()},
            "seven_timer_tier": _seven_timer_tier(avg_st7_seeing, avg_st7_trans),
            "stats": {
                "avg_cloud_cover":     round(avg_cloud, 1)    if avg_cloud is not None else None,
                "avg_high_cloud":      round(avg_hi_cloud, 1) if avg_hi_cloud is not None else None,
                "avg_humidity":        round(avg_rh, 1)       if avg_rh is not None else None,
                "avg_lifted_index":    round(avg_li, 2)       if avg_li is not None else None,
                "night_hours":         len(idxs),
                "seeing_7timer":       avg_st7_seeing,
                "transparency_7timer": avg_st7_trans,
                "bortle_class":        bortle,
            },
        }
        if disq_reasons:
            entry["disqualified"] = "; ".join(disq_reasons)
        results.append(entry)

    return results


def score_all(forecasts: list, tz_str: str, disqualifiers: dict | None = None) -> list:
    """Score all nights across all sites, sorted by date then composite score (desc)."""
    all_nights = []
    for forecast in forecasts:
        all_nights.extend(score_forecast(forecast, tz_str, disqualifiers))
    return sorted(all_nights, key=lambda r: (r["date"], -r["composite"]))


if __name__ == "__main__":
    from db import init_db
    from forecast import fetch_all_forecasts
    from db import get_settings

    init_db()
    print("Fetching forecasts...")
    forecasts = fetch_all_forecasts()

    settings = get_settings()
    tz_str = settings.get("timezone", "America/Chicago")
    print("Scoring...")
    nights = score_all(forecasts, tz_str)

    # Print top 5 nights across all sites
    top = sorted(nights, key=lambda r: -r["composite"])[:5]
    print(f"\n{'Date':<12} {'Site':<30} {'Score':>5}  {'Cloud':>5} {'HiCld':>5} {'Moon':>5} {'LI':>5} {'RH':>5}")
    print("-" * 80)
    for n in top:
        f = n["factors"]
        print(
            f"{n['date']:<12} {n['site']:<30} {n['composite']:>5.1f}"
            f"  {f['cloud_cover']:>5.1f} {f['high_cloud']:>5.1f}"
            f" {f['moon']:>5.1f} {f['lifted_index']:>5.1f} {f['humidity']:>5.1f}"
        )
