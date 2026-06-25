import math

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from db import get_engine, init_db
from utils import dist_display, init_session_settings, render_sidebar

init_db()
init_session_settings()

st.set_page_config(page_icon="🔭", page_title="Visitors — Stargazing Planner")
st.title("🌍 Visitors")
st.caption("Anonymous visit data — IPs are hashed and never stored. Geo data courtesy of ip-api.com.")

# ── Load data ──────────────────────────────────────────────────────────────────
with get_engine().connect() as conn:
    df = pd.read_sql(text("SELECT * FROM visitors ORDER BY visited_at DESC"), conn)

if df.empty:
    st.info("No visitor data yet. Check back after a few visits!")
    render_sidebar()
    st.stop()

# ── Top-level stats ────────────────────────────────────────────────────────────
total_visits   = len(df)
unique_visitors = df["ip_hash"].nunique()
countries      = df["country"].nunique()
today_visits   = len(df[df["visited_at"].dt.date == pd.Timestamp.now().date()])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Visits",      total_visits)
c2.metric("Unique Visitors",   unique_visitors)
c3.metric("Countries",         countries)
c4.metric("Visits Today",      today_visits)

st.divider()

# ── Furthest visitor (from Houston, TX) ───────────────────────────────────────
REF_LAT, REF_LON = 29.76, -95.37  # Houston

def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

df_geo = df.dropna(subset=["lat", "lon"])
if not df_geo.empty:
    df_geo = df_geo.copy()
    df_geo["dist_km"] = df_geo.apply(lambda r: _haversine(REF_LAT, REF_LON, r["lat"], r["lon"]), axis=1)
    furthest = df_geo.loc[df_geo["dist_km"].idxmax()]

    col_far, col_recent = st.columns(2)
    with col_far:
        st.markdown("**🚀 Furthest visitor from Houston**")
        loc_parts = [p for p in [furthest.get("city"), furthest.get("region"), furthest.get("country")] if p]
        st.metric(", ".join(loc_parts), f"{dist_display(furthest['dist_km'])} away")

    with col_recent:
        st.markdown("**🕐 Most recent visit**")
        latest = df.iloc[0]
        loc_parts = [p for p in [latest.get("city"), latest.get("region"), latest.get("country")] if p]
        st.metric(", ".join(loc_parts) or "Unknown", str(latest["visited_at"])[:16])

    st.divider()

# ── Top countries & US states ──────────────────────────────────────────────────
col_countries, col_states = st.columns(2)

with col_countries:
    st.markdown("**🌐 Top countries**")
    top_countries = (
        df.groupby("country").size().reset_index(name="visits")
        .sort_values("visits", ascending=False).head(10)
    )
    st.dataframe(top_countries, hide_index=True, use_container_width=True)

with col_states:
    st.markdown("**🇺🇸 Top US states**")
    us = df[df["country_code"] == "US"]
    if not us.empty:
        top_states = (
            us.groupby("region").size().reset_index(name="visits")
            .sort_values("visits", ascending=False).head(10)
        )
        st.dataframe(top_states, hide_index=True, use_container_width=True)
    else:
        st.caption("No US visits yet.")

st.divider()

# ── World map ──────────────────────────────────────────────────────────────────
st.markdown("**🗺️ Visitor map**")
if not df_geo.empty:
    map_df = (
        df_geo.groupby(["lat", "lon", "city", "region", "country"])
        .size().reset_index(name="visits")
    )
    fig = px.scatter_geo(
        map_df,
        lat="lat", lon="lon",
        size="visits",
        hover_name="city",
        hover_data={"region": True, "country": True, "visits": True, "lat": False, "lon": False},
        projection="natural earth",
        size_max=30,
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=400)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

render_sidebar()
