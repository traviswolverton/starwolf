import requests as _req
import streamlit as st
from streamlit_geolocation import streamlit_geolocation
from timezonefinder import TimezoneFinder

from db import init_db
from osm_import import geocode
from utils import init_session_settings, render_sidebar

_tf = TimezoneFinder()

init_db()
init_session_settings()

st.set_page_config(page_icon="🔭", page_title="Location — Stargazing Planner")
st.title("Your Location")
st.caption(
    "Used to show distances to each site and pre-fill the proximity filter. "
    "Stored in your session only — never saved to a server."
)

loc = st.session_state.user_location


def _set_location(lat: float, lon: float, text_label: str, display: str) -> None:
    st.session_state.user_location = {
        "text": text_label,
        "lat": lat,
        "lon": lon,
        "display": display,
    }
    tz = _tf.timezone_at(lat=lat, lng=lon)
    if tz:
        st.session_state.timezone = tz
        st.session_state.timezone_auto = True


# ── Current location display ──────────────────────────────────────────────────
if st.session_state.user_location:
    l = st.session_state.user_location
    st.info(f"📍 **{l['display']}**  \n`{l['lat']:.4f}, {l['lon']:.4f}`")
    st.caption("Want to add this as a stargazing site? You can do that on the Sites page.")
    st.page_link("pages/1_Sites.py", label="Go to Sites →")
    col_back, col_clear = st.columns([2, 1])
    with col_back:
        st.page_link("Planner.py", label="← Back to Planner")
    with col_clear:
        if st.button("Clear location", use_container_width=True):
            st.session_state.user_location = None
            st.rerun()
    st.divider()

# ── Browser geolocation ────────────────────────────────────────────────────────
st.subheader("Use device location", anchor=False)
st.caption("Tap the button below to let your browser share your current position.")

geo = streamlit_geolocation()

if geo and geo.get("latitude") is not None:
    lat, lon = geo["latitude"], geo["longitude"]
    if (
        not loc
        or abs(loc["lat"] - lat) > 0.0001
        or abs(loc["lon"] - lon) > 0.0001
    ):
        try:
            with st.spinner("Reverse-geocoding…"):
                resp = _req.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={"lat": lat, "lon": lon, "format": "json"},
                    headers={"User-Agent": "stargazing-planner"},
                    timeout=5,
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

        _set_location(lat, lon, display, display)
        st.switch_page("Planner.py")

st.divider()

# ── Manual entry ───────────────────────────────────────────────────────────────
st.subheader("Or enter manually", anchor=False)

loc_input = st.text_input(
    "Address, city, zip, or postal code",
    value=loc["text"] if loc else "",
    placeholder="e.g. Houston, TX  or  77001  or  Calgary, AB",
)

if st.button("Set Location", type="primary"):
    if not loc_input.strip():
        st.warning("Enter a location first.")
    else:
        try:
            with st.spinner("Looking up…"):
                lat, lon, display = geocode(loc_input.strip())
            _set_location(lat, lon, loc_input.strip(), display)
            st.switch_page("Planner.py")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Lookup failed: {e}")

render_sidebar()
