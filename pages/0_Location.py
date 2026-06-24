import streamlit as st
from streamlit_geolocation import streamlit_geolocation

from db import init_db
from osm_import import geocode
from utils import init_session_settings, render_sidebar

init_db()
init_session_settings()

st.set_page_config(page_title="Location — Stargazing Planner")
st.title("Your Location")
st.caption(
    "Used to show distances to each site and pre-fill the proximity filter. "
    "Stored in your session only — never saved to a server."
)

loc = st.session_state.user_location

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
                # Use Nominatim reverse geocode to get a human-readable label
                import requests as _req
                resp = _req.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={"lat": lat, "lon": lon, "format": "json"},
                    headers={"User-Agent": "stargazing-planner"},
                    timeout=5,
                )
                data = resp.json()
                display = data.get("display_name", f"{lat:.4f}, {lon:.4f}")
                # Shorten to city/state level if possible
                addr = data.get("address", {})
                parts = [
                    addr.get("city") or addr.get("town") or addr.get("village"),
                    addr.get("state"),
                    addr.get("country_code", "").upper(),
                ]
                display = ", ".join(p for p in parts if p) or display
        except Exception:
            display = f"{lat:.4f}, {lon:.4f}"

        st.session_state.user_location = {
            "text": display,
            "lat": lat,
            "lon": lon,
            "display": display,
        }
        st.rerun()

st.divider()

# ── Manual entry ───────────────────────────────────────────────────────────────
st.subheader("Or enter manually", anchor=False)

loc_input = st.text_input(
    "Address, city, zip, or postal code",
    value=loc["text"] if loc else "",
    placeholder="e.g. Houston, TX  or  77001  or  Calgary, AB",
)

col_set, col_clear = st.columns([1, 1])
with col_set:
    if st.button("Set Location", use_container_width=True, type="primary"):
        if not loc_input.strip():
            st.warning("Enter a location first.")
        else:
            try:
                with st.spinner("Looking up…"):
                    lat, lon, display = geocode(loc_input.strip())
                st.session_state.user_location = {
                    "text": loc_input.strip(),
                    "lat": lat,
                    "lon": lon,
                    "display": display,
                }
                st.success(f"Location set: {display}")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Lookup failed: {e}")

with col_clear:
    if st.button("Clear", use_container_width=True, disabled=not loc):
        st.session_state.user_location = None
        st.rerun()

if st.session_state.user_location:
    l = st.session_state.user_location
    st.info(f"📍 **{l['display']}**  \n`{l['lat']:.4f}, {l['lon']:.4f}`")

render_sidebar()
