import streamlit as st

from db import init_db
from osm_import import geocode
from utils import init_session_settings, render_sidebar

init_db()
init_session_settings()

st.set_page_config(page_title="Location — Stargazing Planner")
st.title("Your Location")
st.caption(
    "Setting your location enables distance-to-site display in results and "
    "pre-fills the proximity filter on the Sites page. "
    "Location is stored in your session only — never sent to a server or saved."
)

loc = st.session_state.user_location

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
