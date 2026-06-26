from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pydeck as pdk
import streamlit as st
from sqlalchemy import text

from db import get_engine, get_settings
from forecast import _fetch_open_meteo
from scorer import score_forecast
from utils import render_sidebar

st.set_page_config(page_icon="🗺️", page_title="Tonight's Forecast Map — StarWolf", layout="wide")
render_sidebar()

st.title("🗺️ Tonight's Forecast Map")
st.caption("Composite telescope score for tonight across every site in the catalog.")

_CDT = ZoneInfo("America/Chicago")
_WORKERS = 20


def _today_cdt() -> str:
    return datetime.now(_CDT).date().isoformat()


def _score_to_color(score: float | None) -> list[int]:
    if score is None:
        return [150, 150, 150, 140]
    s = max(0.0, min(100.0, score))
    if s >= 50:
        t = (s - 50) / 50          # 0=yellow → 1=green
        r = int(220 - 170 * t)
        g = 200
        b = int(55 * t)
    else:
        t = s / 50                  # 0=red → 1=yellow
        r = 220
        g = int(50 + 150 * t)
        b = int(50 - 50 * t)
    return [r, g, b, 180]


def _load_today_scores(today: str) -> pd.DataFrame | None:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT name, lat, lon, score, computed_at "
                 "FROM site_daily_scores WHERE score_date = :d ORDER BY score DESC NULLS LAST"),
            {"d": today},
        ).fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["name", "lat", "lon", "score", "computed_at"])
    df["color"] = df["score"].apply(_score_to_color)
    df["score_label"] = df["score"].apply(lambda s: f"{s:.0f}" if s is not None else "n/a")
    return df


def _score_one_site(site: dict, tz: str) -> float | None:
    try:
        om = _fetch_open_meteo(site["lat"], site["lon"], forecast_days=2, timezone=tz)
        nights = score_forecast(
            {"site": site, "open_meteo": om, "seven_timer": None, "errors": []},
            tz_str=tz,
        )
        return nights[0]["composite"] if nights else None
    except Exception:
        return None


def _compute_and_store(today: str, tz: str) -> int:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, lat, lon, bortle_class FROM sites WHERE active = 1")
        ).fetchall()
    sites = [dict(r._mapping) for r in rows]

    progress_bar = st.progress(0.0, text="Starting…")
    status      = st.empty()
    total       = len(sites)
    stored      = 0

    with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        future_to_site = {executor.submit(_score_one_site, s, tz): s for s in sites}
        done = 0
        batch = []

        for future in as_completed(future_to_site):
            site  = future_to_site[future]
            score = future.result()
            done += 1

            batch.append({
                "site_id": site["id"],
                "name":    site["name"],
                "lat":     site["lat"],
                "lon":     site["lon"],
                "score":   score,
                "date":    today,
            })

            # Flush to DB every 100 results
            if len(batch) >= 100 or done == total:
                with get_engine().begin() as conn:
                    conn.execute(
                        text("INSERT INTO site_daily_scores "
                             "(site_id, score_date, name, lat, lon, score) "
                             "VALUES (:site_id, :date, :name, :lat, :lon, :score) "
                             "ON CONFLICT (site_id, score_date) DO UPDATE SET "
                             "score = EXCLUDED.score, computed_at = NOW()"),
                        batch,
                    )
                stored += len(batch)
                batch = []

            pct = done / total
            progress_bar.progress(pct, text=f"Scoring sites… {done}/{total}")

    status.empty()
    progress_bar.empty()
    return stored


# ── Page ─────────────────────────────────────────────────────────────────────

today   = _today_cdt()
df      = _load_today_scores(today)
has_data = df is not None and not df.empty

settings  = get_settings()
tz        = settings.get("timezone", "America/Chicago")

# Header row: last refreshed + button
col_info, col_btn = st.columns([3, 1])

with col_info:
    if has_data:
        computed_at = df["computed_at"].iloc[0]
        if hasattr(computed_at, "astimezone"):
            ts = computed_at.astimezone(_CDT).strftime("%-I:%M %p CDT")
        else:
            ts = str(computed_at)
        st.caption(f"Last refreshed today at {ts} · {len(df):,} sites · Bortle ≤ 5 catalog")
    else:
        st.caption("No forecast computed yet for today.")

with col_btn:
    if st.button(
        "🔄 Compute tonight's forecast",
        disabled=has_data,
        help="Already computed today — returns tomorrow." if has_data else "Fetch tonight's forecast for all sites (~30–60 s).",
        use_container_width=True,
    ):
        with st.spinner(""):
            n = _compute_and_store(today, tz)
        st.success(f"Done — {n:,} sites scored.")
        st.rerun()

if not has_data:
    st.info("Click **Compute tonight's forecast** above to generate the map. Takes about 30–60 seconds.")
    st.stop()

# ── Map ───────────────────────────────────────────────────────────────────────

layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position="[lon, lat]",
    get_color="color",
    get_radius=8000,
    radius_min_pixels=3,
    radius_max_pixels=12,
    pickable=True,
)

view = pdk.ViewState(latitude=39.5, longitude=-98.5, zoom=3.5, pitch=0)

tooltip = {
    "html": "<b>{name}</b><br/>Score: <b>{score_label}</b>",
    "style": {"background": "rgba(0,0,0,0.75)", "color": "white", "padding": "8px", "border-radius": "4px"},
}

st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip=tooltip), use_container_width=True)

# ── Legend ────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div style="display:flex;gap:24px;margin-top:8px;font-size:0.85rem">
      <span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:rgb(50,200,55);margin-right:5px"></span>≥ 70 — Worth the drive</span>
      <span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:rgb(135,200,0);margin-right:5px"></span>40–69 — Marginal</span>
      <span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:rgb(220,50,50);margin-right:5px"></span>&lt; 40 — Likely a bust</span>
      <span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:rgb(150,150,150);margin-right:5px"></span>No data</span>
    </div>
    """,
    unsafe_allow_html=True,
)
