import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from sqlalchemy import text
from db import get_engine, get_settings, init_db
from osm_import import _haversine
from utils import KM_TO_MI, dist_display, dist_unit, sync_site_active, init_session_settings, render_sidebar
from release_notes import get_notes_since, get_notes_last_n_days
from visit_tracker import get_cookie_manager, get_last_visit, set_last_visit

init_db()

st.set_page_config(page_icon="🔭", page_title="Stargazing Planner")

st.title("Stargazing Trip Planner")

if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "nights" not in st.session_state:
    st.session_state.nights = None

sync_site_active()
init_session_settings()


def _load_active_sites() -> list[dict]:
    with get_engine().connect() as conn:
        sites = pd.read_sql(text("SELECT * FROM sites ORDER BY name"), conn).to_dict("records")
    active = st.session_state.site_active
    return [s for s in sites if active.get(s["id"], True)]


def _fetch_and_score() -> list:
    from forecast import fetch_site_forecast
    from scorer import score_all
    settings = get_settings()
    forecast_days = int(settings.get("forecast_days", 10))
    timezone = st.session_state.timezone
    disqualifiers = {
        "max_cloud_cover":   st.session_state.disq_max_cloud_cover,
        "max_precip_prob":   st.session_state.disq_max_precip_prob,
        "min_visibility_km": st.session_state.disq_min_visibility_km,
    }
    sites = _load_active_sites()
    forecasts = [fetch_site_forecast(s, forecast_days, timezone) for s in sites]
    return score_all(forecasts, timezone, disqualifiers)


def _score_color(score: float) -> str:
    if score >= 70:
        return "green"
    if score >= 40:
        return "orange"
    return "red"


def _fmt(value, fmt=".0f", suffix="", fallback="—") -> str:
    if value is None:
        return fallback
    try:
        if math.isnan(float(value)):
            return fallback
    except (TypeError, ValueError):
        pass
    return f"{value:{fmt}}{suffix}"


def _norm(value, lo: float, hi: float, higher_is_better: bool = True) -> float | None:
    """Normalise value to [0, 1] where 1 = best quality."""
    if value is None:
        return None
    n = (max(lo, min(hi, float(value))) - lo) / (hi - lo)
    return n if higher_is_better else 1 - n


def _colored_metric(col, label: str, display: str, norm: float | None) -> None:
    """Render a labelled value in col with a red→yellow→green color based on norm."""
    if norm is None:
        color = "#555"
        weight = "400"
    else:
        hue = int(norm * 120)  # 0 = red, 60 = yellow, 120 = green
        color = f"hsl({hue}, 75%, 40%)"
        weight = "700"
    col.markdown(
        f"<div style='text-align:center;padding:4px 0'>"
        f"<div style='font-size:0.75rem;color:#888;margin-bottom:3px'>{label}</div>"
        f"<div style='font-size:1.35rem;font-weight:{weight};color:{color}'>{display}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── What's New ────────────────────────────────────────────────────────────────

if "whats_new_shown" not in st.session_state:
    st.session_state.whats_new_shown = False

if not st.session_state.whats_new_shown:
    _cm = get_cookie_manager()
    _last_visit = get_last_visit(_cm)

    if _last_visit is not None:
        _new_releases = get_notes_since(_last_visit)
        _heading = "What's New Since Your Last Visit"
    else:
        _new_releases = get_notes_last_n_days(7)
        _heading = "What's New in StarWolf"

    if _new_releases:
        # Mark shown and write cookie BEFORE opening the dialog.
        # st.dialog X-dismiss doesn't trigger a rerun, so the True flag persists
        # and prevents reopening when the user next interacts with the page.
        st.session_state.whats_new_shown = True
        set_last_visit(_cm)

        @st.dialog(f"✨ {_heading}")
        def _whats_new_dialog():
            for _r in _new_releases:
                st.markdown(f"**{_r['date']}**")
                for _note in _r.get("notes", []):
                    st.markdown(f"- {_note}")
            st.button("Got it!", type="primary", use_container_width=True, on_click=st.rerun)

        _whats_new_dialog()
    else:
        set_last_visit(_cm)
        st.session_state.whats_new_shown = True


# ── Site selection / results ───────────────────────────────────────────────────

if not st.session_state.show_results:
    active_sites = _load_active_sites()
    total_sites = len(st.session_state.site_active)

    with st.expander("How it works", expanded=False):
        st.markdown("""
Use the pages in the left sidebar to set up your forecast, then come back here and hit **Run Forecast**.

**1 · Location** — Enter your home base (city, zip, or address) to unlock distances and pre-fill the proximity filter on the Sites page.

**2 · Sites** — Choose which dark-sky sites to include. Use *Activate by proximity* or toggle sites individually.

**3 · Preferences** — Set your timezone, minimum score threshold, and hard disqualifier limits (cloud cover, precipitation, visibility).

**4 · Planner** ← you are here — Hit **Run Forecast** to score every upcoming night across all active sites.
""")

    with st.expander("Reading your results", expanded=False):
        st.markdown("""
- **Score (0–100)** — Composite quality across cloud cover, moon phase, stability, and humidity. **70+** is worth the drive; **below 40** is likely a bust.
- **Cloud %** — Average nighttime cloud cover. Under 20% is ideal.
- **Moon** — Combines illumination and hours above the horizon. Higher = darker sky.
- **Seeing / Transparency** — From 7timer (1–8 scale, 1 is best). Only available for the next ~3 days.
- **Heatmap** — All sites and nights at a glance. Green = great, red = poor.
- **Disqualified nights** — Collapsed at the bottom; tap to see what was excluded and why.
""")

    col_loc, col_sites, col_prefs = st.columns(3)

    loc = st.session_state.get("user_location")
    with col_loc:
        with st.container(border=True):
            if loc:
                st.markdown("✅ **Location**")
                st.caption(loc["display"])
            else:
                st.markdown("⚙️ **Location**")
                st.caption("Not set")
                st.page_link("pages/0_Location.py", label="Set location →")

    with col_sites:
        with st.container(border=True):
            if len(active_sites) > 0:
                st.markdown("✅ **Sites**")
                st.caption(f"{len(active_sites)} of {total_sites} active")
            else:
                st.markdown("⚙️ **Sites**")
                st.caption("No sites active")
            if loc:
                is_imperial = st.session_state.units == "imperial"
                if is_imperial:
                    r_display = st.number_input(
                        "Radius (mi)", min_value=30, max_value=3000, step=30,
                        value=round(st.session_state.planner_radius_km * KM_TO_MI),
                        key="planner_radius_input",
                    )
                    r_km = r_display / KM_TO_MI
                else:
                    r_km = st.number_input(
                        "Radius (km)", min_value=50, max_value=5000, step=50,
                        value=st.session_state.planner_radius_km,
                        key="planner_radius_input",
                    )
                    r_display = r_km
                if st.button("Activate nearby", use_container_width=True):
                    try:
                        with get_engine().connect() as conn:
                            all_db_sites = conn.execute(text("SELECT id, lat, lon FROM sites")).fetchall()
                        new_active = {
                            sid: _haversine(loc["lat"], loc["lon"], slat, slon) <= r_km
                            for sid, slat, slon in all_db_sites
                        }
                        n = sum(1 for v in new_active.values() if v)
                        st.session_state.site_active = new_active
                        st.session_state.planner_radius_km = int(r_km)
                        if n:
                            st.toast(f"Activated {n} site(s) within {r_display:.0f} {dist_unit()} of {loc['display'].split(',')[0]}.")
                        else:
                            st.toast(f"No sites found within {r_display:.0f} {dist_unit()} — try a larger radius.", icon="⚠️")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Activation failed: {e}")
            st.page_link("pages/1_Sites.py", label="Manage sites →")

    with col_prefs:
        with st.container(border=True):
            st.markdown("✅ **Preferences**")
            st.caption(f"Threshold {st.session_state.min_score_threshold} · {st.session_state.timezone}")
            st.page_link("pages/2_Preferences.py", label="Adjust →")

    if st.button("Run Forecast", type="primary", use_container_width=True, disabled=not active_sites):
        st.session_state.nights = _fetch_and_score()
        st.session_state.show_results = True
        st.rerun()
    st.caption(f"{len(active_sites)} of {total_sites} sites active · {st.session_state.timezone}")

else:
    if st.button("← Back"):
        st.session_state.show_results = False
        st.rerun()

    nights = st.session_state.nights
    threshold = st.session_state.min_score_threshold

    if not nights:
        st.warning("No forecast data returned. Check that sites are active and APIs are reachable.")
    else:
        today = datetime.now(ZoneInfo(st.session_state.timezone)).date()
        scored       = [n for n in nights if not n.get("disqualified") and datetime.fromisoformat(n["date"]).date() >= today]
        disqualified = [n for n in nights if n.get("disqualified")     and datetime.fromisoformat(n["date"]).date() >= today]
        filtered    = [n for n in scored if n["composite"] >= threshold]

        if not filtered and not disqualified:
            st.info(f"No nights scored above {threshold}. Lower your threshold in Preferences.")
        else:
            if not filtered:
                st.info(f"No nights scored above {threshold}. Lower your threshold in Preferences.")

            if len(filtered) < len(scored):
                st.caption(f"Showing {len(filtered)} of {len(scored)} scored nights (≥ {threshold}); {len(disqualified)} disqualified below.")

            # ── Ranked cards ──────────────────────────────────────────────────
            st.subheader("Best Nights")
            st.info(
                "**† Seeing & Transparency** come from [7timer.info](http://7timer.info), "
                "a free service purpose-built for astronomers that models atmospheric seeing "
                "(how steady the air is) and sky transparency (how clear/dark the sky is). "
                "Both use a **1–8 scale where 1 is best**. "
                "The 7timer forecast only extends ~3 days, so nights beyond that will show — for these two fields — "
                "that's a hard limit of the data source, not a problem with the site.",
                icon="🔭",
            )

            ctrl_l, ctrl_r = st.columns([3, 1])
            with ctrl_l:
                sort_by = st.radio(
                    "Sort by",
                    options=["🔭 Telescope Score", "👁 Naked Eye Score", "Date", "Location"],
                    horizontal=True,
                    key="results_sort",
                )
            with ctrl_r:
                only_7timer = st.toggle("7timer data only", key="results_7timer")

            display = [
                n for n in filtered
                if not only_7timer
                or n["stats"]["seeing_7timer"] is not None
                or n["stats"]["transparency_7timer"] is not None
            ]

            if sort_by == "Date":
                ranked = sorted(display, key=lambda n: (n["date"], -n["composite"]))
            elif sort_by == "Location":
                ranked = sorted(display, key=lambda n: (n["site"], n["date"]))
            elif sort_by == "👁 Naked Eye Score":
                ranked = sorted(display, key=lambda n: -(n.get("naked_eye") or 0))
            else:  # 🔭 Telescope Score
                ranked = sorted(display, key=lambda n: -n["composite"])

            if only_7timer and not ranked:
                st.info("No nights with 7timer data in the current results. 7timer only covers the next ~3 days.")

            # Build distance lookup from user location → site name
            _user_loc = st.session_state.get("user_location")
            if _user_loc:
                _sites = _load_active_sites()
                _site_dist = {
                    s["name"]: _haversine(_user_loc["lat"], _user_loc["lon"], s["lat"], s["lon"])
                    for s in _sites
                }
            else:
                _site_dist = {}

            for night in ranked:
                score  = night["composite"]
                stats  = night["stats"]
                factors = night["factors"]
                date_str = datetime.fromisoformat(night["date"]).strftime("%a %-d %b")
                dist = _site_dist.get(night["site"])
                dist_str = f" · {dist_display(dist)}" if dist is not None else ""
                tel_color = _score_color(score)
                naked_eye = night.get("naked_eye")
                eye_color = _score_color(naked_eye) if naked_eye is not None else "gray"
                naked_eye_str = f"**{naked_eye:.0f}**" if naked_eye is not None else "—"
                label = (
                    f"🔭 :{tel_color}[**{score:.0f}**]"
                    f"  👁 :{eye_color}[{naked_eye_str}]"
                    f" &nbsp; {date_str} &nbsp;·&nbsp; {night['site']}{dist_str}"
                )
                with st.expander(label):
                    c1, c2, c3, c4 = st.columns(4)
                    _colored_metric(c1, "Cloud Cover", _fmt(stats["avg_cloud_cover"], suffix="%"),   _norm(stats["avg_cloud_cover"],          0, 100, False))
                    _colored_metric(c2, "High Cloud",  _fmt(stats["avg_high_cloud"],  suffix="%"),   _norm(stats["avg_high_cloud"],           0, 100, False))
                    _colored_metric(c3, "Moon Score",  _fmt(factors["moon"]),                        _norm(factors["moon"],                   0, 100, True))
                    _colored_metric(c4, "Night Hours", _fmt(stats["night_hours"], ".0f", "h"),       _norm(stats["night_hours"],              4,  12, True))
                    c5, c6, c7, c8 = st.columns(4)
                    _colored_metric(c5, "Humidity",    _fmt(stats["avg_humidity"],    suffix="%"),   _norm(stats["avg_humidity"],             0, 100, False))
                    _colored_metric(c6, "Stability",   _fmt(factors["lifted_index"]),                _norm(factors["lifted_index"],           0, 100, True))
                    _colored_metric(c7, "Seeing †",    _fmt(stats["seeing_7timer"],   ".1f"),        _norm(stats["seeing_7timer"],            1,   8, False))
                    _colored_metric(c8, "Transp. †",   _fmt(stats["transparency_7timer"], ".1f"),   _norm(stats["transparency_7timer"],      1,   8, False))
                    (c9,) = st.columns(1)
                    bortle = stats.get("bortle_class")
                    bortle_display = f"Class {bortle}" if bortle is not None else "—"
                    bortle_norm = _norm(bortle, 1, 9, higher_is_better=False) if bortle is not None else None
                    _colored_metric(c9, "Bortle", bortle_display, bortle_norm)

            # ── Calendar heatmap ──────────────────────────────────────────────
            st.subheader("Night Quality Heatmap")
            heatmap_score = st.radio("Heatmap score", ["🔭 Telescope", "👁 Naked Eye"], horizontal=True, key="heatmap_score")
            score_key = "composite" if heatmap_score == "🔭 Telescope" else "naked_eye"
            pivot = (
                pd.DataFrame([{"site": n["site"], "date": n["date"], "score": n[score_key]} for n in filtered])
                .pivot_table(index="site", columns="date", values="score", aggfunc="first")
            )
            pivot.columns = [datetime.fromisoformat(d).strftime("%a %-d %b") for d in pivot.columns]

            tick_step = (100 - threshold) // 4 or 1
            tickvals = list(range(threshold, 101, tick_step))

            fig = px.imshow(
                pivot,
                color_continuous_scale="RdYlGn",
                zmin=threshold,
                zmax=100,
                aspect="auto",
                labels={"color": "Score", "x": "", "y": ""},
            )
            fig.update_layout(
                coloraxis_colorbar=dict(title="Score", tickvals=tickvals),
                margin=dict(l=0, r=0, t=40, b=0),
                xaxis=dict(side="top"),
                height=max(200, len(pivot) * 55),
            )
            fig.update_traces(
                hovertemplate="<b>%{y}</b><br>%{x}<br>Score: %{z:.1f}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        if disqualified:
            with st.expander(f"Disqualified nights ({len(disqualified)})"):
                st.caption("These nights were excluded from scoring because they exceeded one or more hard disqualifier thresholds set in Preferences.")
                disq_rows = []
                for n in sorted(disqualified, key=lambda x: (x["date"], x["site"])):
                    disq_rows.append({
                        "Date": datetime.fromisoformat(n["date"]).strftime("%a %-d %b"),
                        "Site": n["site"],
                        "Reason": n["disqualified"],
                    })
                st.dataframe(
                    pd.DataFrame(disq_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Reason": st.column_config.TextColumn("Reason", width="large"),
                    },
                )


render_sidebar()
