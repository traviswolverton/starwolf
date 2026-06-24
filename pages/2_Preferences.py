import streamlit as st

from db import get_settings, init_db
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

st.divider()
if st.button("Reset to defaults"):
    settings = get_settings()
    st.session_state.timezone = settings.get("timezone", "America/Chicago")
    st.session_state.min_score_threshold = int(settings.get("min_score_threshold", "40"))
    st.session_state.disq_max_cloud_cover = int(settings.get("disq_max_cloud_cover", "85"))
    st.session_state.disq_max_precip_prob = int(settings.get("disq_max_precip_prob", "40"))
    st.session_state.disq_min_visibility_km = int(settings.get("disq_min_visibility_km", "10"))
    st.session_state.units = "metric"
    st.rerun()

render_sidebar()
