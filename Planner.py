from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_connection, get_settings, init_db
from utils import sync_site_active, init_session_settings

init_db()

st.set_page_config(page_title="Stargazing Planner")

st.image("starwolf-logo.svg", width=200)
st.title("Stargazing Trip Planner")

if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "nights" not in st.session_state:
    st.session_state.nights = None

sync_site_active()
init_session_settings()


def _load_active_sites() -> list[dict]:
    con = get_connection()
    sites = pd.read_sql("SELECT * FROM sites ORDER BY name", con).to_dict("records")
    con.close()
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
    return f"{value:{fmt}}{suffix}" if value is not None else fallback


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


# ── Site selection / results ───────────────────────────────────────────────────

if not st.session_state.show_results:
    active_sites = _load_active_sites()
    total_sites = len(st.session_state.site_active)

    st.markdown("""
### How it works

Use the pages in the left sidebar to set up your forecast, then come back here and hit **Run Forecast**.

| Step | Page | What to do |
|------|------|------------|
| 1 | **Sites** | Pick which dark-sky sites to include. Use *Activate by proximity* to find sites near your location, or toggle individual sites on/off in the site list. |
| 2 | **Preferences** | Set your timezone (used for night/day boundaries) and a minimum score threshold to filter out poor nights. |
| 3 | **Planner** ← you are here | Hit **Run Forecast** to fetch weather data for all active sites and score every upcoming night. |

---

### Reading your results

After running a forecast you'll see a ranked table and a heatmap.

- **Score (0–100)** — Composite night quality weighted across cloud cover, moon, atmospheric stability, and humidity. **70+** is worth the drive; **below 40** is likely a bust.
- **Cloud %** — Average nighttime cloud cover. Under 20% is ideal; above 50% is likely a washout.
- **Moon** — Combines illumination percentage and hours above the horizon. Higher is better (a darker sky).
- **Heatmap** — Compare all sites across all nights at a glance. Green = great, red = poor.

Scores only use nighttime hours (when `is_day = 0` at each site's location), so daytime weather never skews your results.
""")

    st.divider()
    st.caption(
        f"{len(active_sites)} of {total_sites} site(s) active this session — "
        f"manage in **Sites**, adjust timezone and score threshold in **Preferences**."
    )

    if st.button("Run Forecast", type="primary", disabled=not active_sites):
        with st.spinner("Fetching forecasts…"):
            st.session_state.nights = _fetch_and_score()
        st.session_state.show_results = True
        st.rerun()

else:
    if st.button("← Back"):
        st.session_state.show_results = False
        st.rerun()

    nights = st.session_state.nights
    threshold = st.session_state.min_score_threshold

    if not nights:
        st.warning("No forecast data returned. Check that sites are active and APIs are reachable.")
    else:
        scored      = [n for n in nights if not n.get("disqualified")]
        disqualified = [n for n in nights if n.get("disqualified")]
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
            ranked = sorted(filtered, key=lambda n: -n["composite"])
            for night in ranked:
                score  = night["composite"]
                stats  = night["stats"]
                factors = night["factors"]
                date_str = datetime.fromisoformat(night["date"]).strftime("%a %-d %b")
                color  = _score_color(score)
                label  = f":{color}[**{score:.0f}**] &nbsp; {date_str} &nbsp;·&nbsp; {night['site']}"
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
            st.info(
                "**† Seeing & Transparency** come from [7timer.info](http://7timer.info), "
                "a free service purpose-built for astronomers that models atmospheric seeing "
                "(how steady the air is) and sky transparency (how clear/dark the sky is). "
                "Both use a **1–8 scale where 1 is best**. "
                "The 7timer forecast only extends ~3 days, so nights beyond that will show — for these two fields — "
                "that's a hard limit of the data source, not a problem with the site.",
                icon="🔭",
            )

            # ── Calendar heatmap ──────────────────────────────────────────────
            st.subheader("Night Quality Heatmap")
            pivot = (
                pd.DataFrame([{"site": n["site"], "date": n["date"], "score": n["composite"]} for n in filtered])
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
            )
            fig.update_traces(
                hovertemplate="<b>%{y}</b><br>%{x}<br>Score: %{z:.1f}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

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


st.divider()
st.markdown("""
**Data sources & credits**
| | |
|---|---|
| **Weather & atmosphere** | [Open-Meteo](https://open-meteo.com) — free, no API key, 16-day hourly forecast |
| **Astronomical seeing** | [7timer!](http://www.7timer.info) — purpose-built for astronomers |
| **Moon phase / rise / set** | `astral` Python library — fully offline |
| **Dark sky site data** | [IDA / DarkSky International](https://darksky.org) — designated places dataset |
| **Geocoding** | [Nominatim / OpenStreetMap](https://nominatim.org) & [Natural Resources Canada](https://geogratis.gc.ca) |
| **App** | Built with [Streamlit](https://streamlit.io) · AI assistance by [Claude](https://anthropic.com) |
| **Authors** | Seth & Travis Wolverton |
| **Source** | [gitea.wolvertons.net/travis/stargazing-app](https://gitea.wolvertons.net/travis/stargazing-app) |
""")
