import pandas as pd
import streamlit as st

from sqlalchemy import text
from db import get_engine, get_settings, init_db
from scorer import NAKED_EYE_WEIGHTS
from utils import KM_TO_MI, init_session_settings, render_sidebar

init_db()
init_session_settings()

st.set_page_config(page_icon="🔭", page_title="Preferences — Stargazing Planner")
st.title("Preferences")
st.caption("These settings apply to your current session only and reset when you close the tab.")

# ── Units ──────────────────────────────────────────────────────────────────────

st.subheader("Units")
units = st.radio(
    "Measurement system",
    options=["metric", "imperial"],
    format_func=lambda x: "Metric (km, m)" if x == "metric" else "Imperial (mi, ft)",
    index=0 if st.session_state.units == "metric" else 1,
    horizontal=True,
    label_visibility="collapsed",
)
if units != st.session_state.units:
    st.session_state.units = units
    st.rerun()

# ── Timezone ───────────────────────────────────────────────────────────────────

st.subheader("Timezone")
COMMON_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
    "America/Phoenix",
    "America/Toronto",
    "America/Vancouver",
    "America/Edmonton",
    "America/Halifax",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Australia/Sydney",
    "Pacific/Auckland",
    "UTC",
]

if st.session_state.get("timezone_auto"):
    st.caption(f"Auto-detected from your location: **{st.session_state.timezone}**. Override below if needed.")

tz_options = COMMON_TIMEZONES[:]
if st.session_state.timezone not in tz_options:
    tz_options.insert(0, st.session_state.timezone)

tz = st.selectbox(
    "Timezone",
    options=tz_options,
    index=tz_options.index(st.session_state.timezone),
    help="Used for night/day boundary calculations and forecast display.",
    label_visibility="collapsed",
)
if tz != st.session_state.timezone:
    st.session_state.timezone = tz
    st.session_state.timezone_auto = False
    st.rerun()

# ── Minimum Score Threshold ────────────────────────────────────────────────────

st.subheader("Minimum Score Threshold")
threshold = st.slider(
    "Hide nights scoring below this value",
    min_value=0,
    max_value=100,
    value=st.session_state.min_score_threshold,
    help="Nights scoring below this threshold are hidden on the Planner page.",
)
if threshold != st.session_state.min_score_threshold:
    st.session_state.min_score_threshold = threshold

# ── Hard Disqualifiers ─────────────────────────────────────────────────────────

st.subheader("Hard Disqualifiers")
st.caption(
    "Nights that exceed any of these thresholds are excluded from results entirely, "
    "regardless of their composite score. Drag all the way to the maximum to effectively disable a rule."
)

max_cloud = st.slider(
    "Max cloud cover (%)",
    min_value=50, max_value=100,
    value=st.session_state.disq_max_cloud_cover,
    help="Exclude nights where average nighttime cloud cover exceeds this value.",
)
if max_cloud != st.session_state.disq_max_cloud_cover:
    st.session_state.disq_max_cloud_cover = max_cloud

max_precip = st.slider(
    "Max precipitation probability (%)",
    min_value=0, max_value=100,
    value=st.session_state.disq_max_precip_prob,
    help="Exclude nights where average nighttime precipitation probability exceeds this value.",
)
if max_precip != st.session_state.disq_max_precip_prob:
    st.session_state.disq_max_precip_prob = max_precip

is_imperial = st.session_state.units == "imperial"
if is_imperial:
    stored_km = st.session_state.disq_min_visibility_km
    slider_val = round(stored_km * KM_TO_MI)
    min_vis_display = st.slider(
        "Min visibility (mi)",
        min_value=0, max_value=32,
        value=slider_val,
        help="Exclude nights where average nighttime visibility falls below this value. Set to 0 to disable.",
    )
    min_vis_km = round(min_vis_display / KM_TO_MI)
else:
    min_vis_km = st.slider(
        "Min visibility (km)",
        min_value=0, max_value=50,
        value=st.session_state.disq_min_visibility_km,
        help="Exclude nights where average nighttime visibility falls below this value. Set to 0 to disable.",
    )
if min_vis_km != st.session_state.disq_min_visibility_km:
    st.session_state.disq_min_visibility_km = min_vis_km

# ── Reset ──────────────────────────────────────────────────────────────────────

# ── Scoring Weights ────────────────────────────────────────────────────────────

st.divider()
st.subheader("Scoring Weights")
st.caption(
    "How each factor contributes to the two composite scores. "
    "Telescope weights are stored in the database; naked eye weights are fixed constants."
)

_FACTOR_LABELS = {
    "cloud_cover":  "Cloud Cover",
    "high_cloud":   "High Cloud",
    "moon":         "Moon",
    "lifted_index": "Stability (LI)",
    "humidity":     "Humidity",
}

with get_engine().connect() as _conn:
    _tel_rows = _conn.execute(
        text("SELECT factor, weight, description FROM scoring_weights ORDER BY weight DESC")
    ).fetchall()

_col_tel, _col_eye = st.columns(2)

with _col_tel:
    st.markdown("**🔭 Telescope**")
    st.dataframe(
        pd.DataFrame([
            {
                "Factor":  _FACTOR_LABELS.get(r.factor, r.factor),
                "Weight":  f"{r.weight * 100:.0f}%",
                "Notes":   r.description,
            }
            for r in _tel_rows
        ]),
        use_container_width=True,
        hide_index=True,
    )

with _col_eye:
    st.markdown("**👁 Naked Eye**")
    _desc = {r.factor: r.description for r in _tel_rows}
    st.dataframe(
        pd.DataFrame([
            {
                "Factor":  _FACTOR_LABELS.get(f, f),
                "Weight":  f"{w * 100:.0f}%",
                "Notes":   _desc.get(f, ""),
            }
            for f, w in sorted(NAKED_EYE_WEIGHTS.items(), key=lambda x: -x[1])
        ]),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Plus a Bortle class modifier (0.55–1.0×) applied to the total.")

# ── Reset ──────────────────────────────────────────────────────────────────────

st.divider()
if st.button("Reset to defaults"):
    settings = get_settings()
    loc = st.session_state.get("user_location")
    if loc:
        from timezonefinder import TimezoneFinder
        tz_auto = TimezoneFinder().timezone_at(lat=loc["lat"], lng=loc["lon"])
        if tz_auto:
            st.session_state.timezone = tz_auto
            st.session_state.timezone_auto = True
        else:
            st.session_state.timezone = settings.get("timezone", "America/Chicago")
            st.session_state.timezone_auto = False
    else:
        st.session_state.timezone = settings.get("timezone", "America/Chicago")
        st.session_state.timezone_auto = False
    st.session_state.min_score_threshold = int(settings.get("min_score_threshold", "40"))
    st.session_state.disq_max_cloud_cover = int(settings.get("disq_max_cloud_cover", "85"))
    st.session_state.disq_max_precip_prob = int(settings.get("disq_max_precip_prob", "40"))
    st.session_state.disq_min_visibility_km = int(settings.get("disq_min_visibility_km", "10"))
    st.session_state.units = "metric"
    st.rerun()

render_sidebar()
