import requests as _req
import streamlit as st
from streamlit_geolocation import streamlit_geolocation
from sqlalchemy import text

from db import get_engine, init_db
from osm_import import geocode, _haversine
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


def _set_location(lat: float, lon: float, text_label: str, display: str) -> None:
    st.session_state.user_location = {
        "text": text_label,
        "lat": lat,
        "lon": lon,
        "display": display,
    }
    st.session_state._prompt_add_site = True


def _nearby_site(lat: float, lon: float, threshold_km: float = 2.0):
    """Return the nearest existing site if it's within threshold_km, else None."""
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT name, lat, lon FROM sites")).fetchall()
    best, best_dist = None, float("inf")
    for name, slat, slon in rows:
        d = _haversine(lat, lon, slat, slon)
        if d < best_dist:
            best, best_dist = name, d
    if best_dist <= threshold_km:
        return best, best_dist
    return None, None


# ── Add-as-site prompt ────────────────────────────────────────────────────────
if st.session_state.get("_prompt_add_site") and st.session_state.user_location:
    l = st.session_state.user_location
    st.success(f"📍 Location set: **{l['display']}**")

    nearby, nearby_dist = _nearby_site(l["lat"], l["lon"])
    if nearby:
        st.info(
            f"**{nearby}** is already in your site catalog ({nearby_dist:.1f} km away). "
            "You can still add your home base as a separate site if you'd like.",
            icon="ℹ️",
        )

    with st.container(border=True):
        st.markdown("**Add your home base as a stargazing site?**")
        st.caption(
            "It will appear in forecast results and proximity filtering just like any other site."
        )
        site_name = st.text_input(
            "Site name",
            value=l["display"].split(",")[0].strip(),
            max_chars=80,
            key="_new_site_name",
        )
        col_yes, col_skip = st.columns(2)
        with col_yes:
            if st.button("Add as site", type="primary", use_container_width=True):
                if not site_name.strip():
                    st.warning("Enter a name for the site.")
                else:
                    with get_engine().begin() as conn:
                        conn.execute(
                            text(
                                "INSERT INTO sites (name, lat, lon, notes, active) "
                                "VALUES (:name, :lat, :lon, :notes, 1)"
                            ),
                            {
                                "name": site_name.strip(),
                                "lat": l["lat"],
                                "lon": l["lon"],
                                "notes": "Home base",
                            },
                        )
                    del st.session_state._prompt_add_site
                    # Force site_active to re-sync on next load
                    st.session_state.pop("site_active", None)
                    st.success(f"**{site_name.strip()}** added to your site catalog.")
                    st.rerun()
        with col_skip:
            if st.button("Skip", use_container_width=True):
                del st.session_state._prompt_add_site
                st.rerun()

    st.divider()

# ── Current location display ──────────────────────────────────────────────────
if st.session_state.user_location and not st.session_state.get("_prompt_add_site"):
    l = st.session_state.user_location
    st.info(f"📍 **{l['display']}**  \n`{l['lat']:.4f}, {l['lon']:.4f}`")
    if st.button("Clear location"):
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
        st.rerun()

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
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Lookup failed: {e}")

render_sidebar()
