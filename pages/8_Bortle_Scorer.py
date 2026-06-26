import pandas as pd
import requests
import streamlit as st

from bortle_lookup import lookup_bortle
from utils import render_sidebar

st.set_page_config(page_icon="🌑", page_title="Bortle Scorer — StarWolf")
render_sidebar()

st.title("🌑 Bortle Scorer")
st.caption("Look up the light pollution level for any location — enter an address or coordinates.")

_BORTLE_DESC = {
    1: ("Excellent dark sky",        "The zodiacal light, gegenschein, and zodiacal band are all visible. M33 is direct-vision object. Scorpius and Sagittarius cast shadows."),
    2: ("Truly dark site",           "Airglow is weakly visible. M33 is easily seen. Limiting magnitude ~7.1–7.5."),
    3: ("Rural sky",                 "Some light pollution evident on the horizon. Milky Way still shows tremendous structure. Limiting magnitude ~6.6–7.0."),
    4: ("Rural / suburban transition","Light domes visible in several directions. Milky Way still impressive but lacks fine detail. Limiting magnitude ~6.1–6.5."),
    5: ("Suburban sky",              "Only hints of the Milky Way visible toward zenith. Light pollution obvious in most directions. Limiting magnitude ~5.6–6.0."),
    6: ("Bright suburban sky",       "Milky Way only visible near zenith. M33 invisible. Limiting magnitude ~5.1–5.5."),
    7: ("Suburban / urban transition","Milky Way barely visible. Clouds are brighter than the sky. Limiting magnitude ~4.6–5.0."),
    8: ("City sky",                  "Sky is orange/grey. Stars barely visible. Limiting magnitude ~4.1–4.5."),
    9: ("Inner-city sky",            "Entire sky is bright. Only the brightest stars visible. Limiting magnitude <4.0."),
}

_BORTLE_COLOR = {
    1: "#1a1a3e", 2: "#1a2a4e", 3: "#1e3a5f",
    4: "#2e5a3f", 5: "#6e7a1f", 6: "#8e6a0f",
    7: "#9e4a0f", 8: "#ae2a0f", 9: "#be0a0f",
}


def _geocode(address: str) -> tuple[float, float] | None:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "StarWolf-App/1.0"},
            timeout=10,
        )
        results = r.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        return None


# ── Input ────────────────────────────────────────────────────────────────────

tab_addr, tab_coords = st.tabs(["📍 Address", "🌐 Coordinates"])

lat = lon = None

with tab_addr:
    address = st.text_input("Enter an address, city, or place name", placeholder="e.g. Big Bend National Park, TX")
    if st.button("Look up", key="addr_btn") and address:
        with st.spinner("Geocoding…"):
            result = _geocode(address)
        if result:
            lat, lon = result
            st.success(f"Found: {lat:.5f}, {lon:.5f}")
        else:
            st.error("Address not found. Try a more specific location or use the Coordinates tab.")

with tab_coords:
    col1, col2 = st.columns(2)
    with col1:
        lat_in = st.number_input("Latitude",  min_value=-90.0,  max_value=90.0,  value=30.67, format="%.5f")
    with col2:
        lon_in = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-104.02, format="%.5f")
    if st.button("Score this location", key="coords_btn"):
        lat, lon = lat_in, lon_in

# ── Results ──────────────────────────────────────────────────────────────────

if lat is not None and lon is not None:
    st.divider()

    try:
        data   = lookup_bortle(lat, lon)
        bortle = data["bortle"]
        sqm    = data["sqm"]
        label, desc = _BORTLE_DESC[bortle]
        color  = _BORTLE_COLOR[bortle]

        col_score, col_detail = st.columns([1, 2])

        with col_score:
            st.markdown(
                f"""
                <div style="background:{color};border-radius:12px;padding:24px 16px;text-align:center;color:white;">
                    <div style="font-size:3rem;font-weight:700;line-height:1">{bortle}</div>
                    <div style="font-size:0.85rem;margin-top:4px;opacity:0.85">Bortle Class</div>
                    <hr style="border-color:rgba(255,255,255,0.3);margin:12px 0">
                    <div style="font-size:1.4rem;font-weight:600">{sqm}</div>
                    <div style="font-size:0.75rem;opacity:0.85">mag/arcsec² (SQM)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_detail:
            st.subheader(label)
            st.write(desc)
            st.caption(f"Coordinates: {lat:.5f}, {lon:.5f}")

        st.subheader("Location")
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=9)

    except ValueError as e:
        st.error(f"No data for this location: {e}")
    except FileNotFoundError:
        st.error("World Atlas GeoTIFF is not available on this server.")
