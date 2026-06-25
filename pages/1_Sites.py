import os

import pandas as pd
import streamlit as st

from sqlalchemy import text
from bortle_lookup import lookup_bortle, WORLD_ATLAS_PATH
from db import get_engine, init_db
from osm_import import _haversine, find_nearest_existing, geocode, import_sites
from utils import KM_TO_MI, dist_unit, km_to_display, sync_site_active, init_session_settings, render_sidebar

_ATLAS_PRESENT = os.path.exists(WORLD_ATLAS_PATH)

init_db()
sync_site_active()
init_session_settings()

st.set_page_config(page_icon="🔭", page_title="Sites — Stargazing Planner")
st.title("Dark-Sky Sites")

if "addr_result" not in st.session_state:
    st.session_state.addr_result = None

is_imperial = st.session_state.units == "imperial"
is_admin = bool(st.session_state.get("admin_authenticated"))

# ── Activate by proximity ──────────────────────────────────────────────────────

st.subheader("Activate by Proximity")

_loc = st.session_state.user_location
if not _loc:
    st.info("Set your location first to activate nearby sites.", icon="📍")
    st.page_link("pages/0_Location.py", label="Set your location →")
else:
    st.caption(f"From: **{_loc['display']}**")
    if is_imperial:
        prox_radius_display = st.slider("Radius (mi)", min_value=6, max_value=3000, value=300, step=10)
        prox_radius_km = prox_radius_display / KM_TO_MI
    else:
        prox_radius_km = st.slider("Radius (km)", min_value=10, max_value=5000, value=500, step=10)
        prox_radius_display = prox_radius_km

    if st.button("Activate Sites in Range"):
        try:
            with st.spinner("Updating…"):
                with get_engine().connect() as conn:
                    all_sites = conn.execute(text("SELECT id, name, lat, lon FROM sites")).fetchall()
                new_active = dict(st.session_state.site_active)
                for site_id, name, slat, slon in all_sites:
                    new_active[site_id] = _haversine(_loc["lat"], _loc["lon"], slat, slon) <= prox_radius_km
                st.session_state.site_active = new_active
            activated = sum(1 for site_id, _, slat, slon in all_sites if new_active[site_id])
            st.success(f"Activated {activated} site(s) within {prox_radius_display:.0f} {dist_unit()} of {_loc['display'].split(',')[0]}.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {e}")

def _bortle_ui(lat: float, lon: float, key: str) -> int | None:
    """Render Bortle number_input + Look Up button. Returns the current value (or None)."""
    col_b, col_btn = st.columns([2, 1])
    with col_b:
        bortle_val = st.number_input(
            "Bortle Class (required)",
            min_value=1, max_value=9, step=1,
            value=st.session_state.get(key),
            key=f"{key}_input",
            help="1 = darkest skies, 9 = inner city.",
        )
    with col_btn:
        st.write("")
        st.write("")
        if _ATLAS_PRESENT:
            if st.button("🔭 Look Up", key=f"{key}_lookup"):
                try:
                    with st.spinner("Reading sky brightness data…"):
                        result = lookup_bortle(lat, lon)
                    st.session_state[key] = result["bortle"]
                    st.session_state[f"{key}_input"] = result["bortle"]
                    st.session_state[f"{key}_sqm"] = result["sqm"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Lookup failed: {e}")
        else:
            st.button("🔭 Look Up", disabled=True, key=f"{key}_lookup",
                      help=f"GeoTIFF not found at {WORLD_ATLAS_PATH}. Run scripts/download_world_atlas.sh.")
    if bortle_val is not None:
        st.session_state[key] = int(bortle_val)
    sqm = st.session_state.get(f"{key}_sqm")
    if sqm is not None:
        st.caption(f"SQM from lookup: {sqm} mag/arcsec²")
    return bortle_val


# ── Add home base ─────────────────────────────────────────────────────────────

if _loc:
    dup = find_nearest_existing(_loc["lat"], _loc["lon"])
    with st.expander("Add your location as a site", expanded=not dup):
        if dup:
            dup_dist = f"{round(dup[1] * KM_TO_MI)} mi" if is_imperial else f"{dup[1]:.0f} km"
            st.caption(f"⚠️ Possible duplicate: **{dup[0]}** is already in the catalog ({dup_dist} away).")
        home_name = st.text_input(
            "Site name",
            value=_loc["display"].split(",")[0].strip(),
            max_chars=80,
            key="home_site_name",
        )
        home_bortle = _bortle_ui(_loc["lat"], _loc["lon"], "home_bortle")
        if not _ATLAS_PRESENT:
            st.caption(f"GeoTIFF not present — run `scripts/download_world_atlas.sh` to enable Look Up.")
        can_add = bool(home_name.strip()) and home_bortle is not None
        if st.button("Add as site", type="primary", disabled=not can_add):
            import_sites([{
                "name":        home_name.strip(),
                "lat":         _loc["lat"],
                "lon":         _loc["lon"],
                "bortle_class": int(home_bortle),
                "elevation_m": None,
                "notes":       _loc["display"],
            }])
            st.session_state.pop("home_bortle", None)
            st.success(f"**{home_name.strip()}** added.")
            st.rerun()

# ── Bulk activate / deactivate ────────────────────────────────────────────────

col_on, col_off = st.columns(2)
with col_on:
    if st.button("Activate All", use_container_width=True):
        st.session_state.site_active = {k: True for k in st.session_state.site_active}
        st.rerun()
with col_off:
    if st.button("Deactivate All", use_container_width=True):
        st.session_state.site_active = {k: False for k in st.session_state.site_active}
        st.rerun()


# ── Site list editor ───────────────────────────────────────────────────────────

def load_sites() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(text("SELECT * FROM sites ORDER BY name"), conn)
    active = st.session_state.site_active
    df["active"] = df["id"].map(lambda i: active.get(i, True)).astype(bool)
    df["map"] = df.apply(
        lambda r: f"https://www.openstreetmap.org/?mlat={r['lat']}&mlon={r['lon']}#map=12/{r['lat']}/{r['lon']}",
        axis=1,
    )
    loc = st.session_state.get("user_location")
    if loc:
        df["dist_km"] = df.apply(
            lambda r: round(_haversine(loc["lat"], loc["lon"], r["lat"], r["lon"])), axis=1
        )
    return df


def save_sites(df: pd.DataFrame) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM sites"))
        conn.execute(
            text("INSERT INTO sites (name, lat, lon, bortle_class, elevation_m, notes, active) "
                 "VALUES (:name, :lat, :lon, :bortle, :elev, :notes, :active)"),
            [{"name": row["name"], "lat": row["lat"], "lon": row["lon"],
              "bortle": row.get("bortle_class"), "elev": row.get("elevation_m"),
              "notes": row.get("notes"), "active": int(row["active"])}
             for _, row in df.iterrows()],
        )
        rows = conn.execute(text("SELECT id, active FROM sites")).fetchall()
    st.session_state.site_active = {row[0]: bool(row[1]) for row in rows}


st.subheader("Site List")
if is_admin:
    st.info(
        "The **Active** column reflects your current session. "
        "Saving persists name/coordinate edits to the shared catalog and sets the default active state for new sessions.",
        icon="ℹ️",
    )
else:
    st.info("Site catalog is read-only. Log in as Admin to add, edit, or remove sites.", icon="🔒")

sites_df = load_sites()
has_dist = "dist_km" in sites_df.columns

# Convert dist column to display units
if has_dist:
    sites_df["dist_km"] = sites_df["dist_km"].apply(
        lambda v: round(v * KM_TO_MI) if is_imperial else v
    )

col_order = ["map", "name", "lat", "lon", "bortle_class", "elevation_m", "notes", "active"]
if has_dist:
    col_order = ["dist_km"] + col_order

col_config = {
    "map":          st.column_config.LinkColumn("Map", display_text="🗺️", disabled=True, width="small"),
    "name":         st.column_config.TextColumn("Name", required=True),
    "lat":          st.column_config.NumberColumn("Latitude",  format="%.4f", min_value=-90,  max_value=90),
    "lon":          st.column_config.NumberColumn("Longitude", format="%.4f", min_value=-180, max_value=180),
    "bortle_class": st.column_config.NumberColumn("Bortle Class", min_value=1, max_value=9, step=1),
    "elevation_m":  st.column_config.NumberColumn("Elevation (m)"),
    "notes":        st.column_config.TextColumn("Notes", width="large"),
    "active":       st.column_config.CheckboxColumn("Active"),
}
if has_dist:
    col_config["dist_km"] = st.column_config.NumberColumn(
        f"Dist ({'mi' if is_imperial else 'km'})", disabled=True
    )

edited_sites = st.data_editor(
    sites_df,
    num_rows="dynamic" if is_admin else "fixed",
    disabled=not is_admin,
    use_container_width=True,
    column_order=col_order,
    column_config=col_config,
    key="sites_editor",
)
if is_admin and st.button("Save Sites"):
    save_sites(
        edited_sites.drop(columns=["dist_km", "map"], errors="ignore").dropna(subset=["name"])
    )
    st.success("Sites saved.")


# ── Add Site by Address ────────────────────────────────────────────────────────

with st.expander("Add Site by Address"):
    addr_input = st.text_input("Address, place name, zip, or postal code", key="addr_input")

    if st.button("Look Up Address"):
        if not addr_input.strip():
            st.warning("Enter an address to look up.")
        else:
            try:
                with st.spinner("Looking up…"):
                    lat, lon, display = geocode(addr_input.strip())
                st.session_state.addr_result = {"lat": lat, "lon": lon, "display": display}
                st.session_state.pop("addr_bortle", None)
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Lookup failed: {e}")

    if st.session_state.addr_result:
        r = st.session_state.addr_result
        st.success(f"Resolved: {r['display']}")
        st.caption(f"Lat: {r['lat']:.5f}  |  Lon: {r['lon']:.5f}")

        dup = find_nearest_existing(r["lat"], r["lon"])
        if dup:
            dup_dist = f"{round(dup[1] * KM_TO_MI)} mi" if is_imperial else f"{dup[1]} km"
            st.warning(f"⚠️ Possible duplicate: {dup[0]} ({dup_dist} away in DB)")

        site_name = st.text_input("Site name", value=r["display"].split(",")[0].strip(), key="addr_site_name")
        addr_bortle = _bortle_ui(r["lat"], r["lon"], "addr_bortle")

        can_add = bool(site_name.strip()) and addr_bortle is not None
        if st.button("Add Site", type="primary", disabled=not can_add):
            import_sites([{
                "name":        site_name.strip(),
                "lat":         r["lat"],
                "lon":         r["lon"],
                "bortle_class": int(addr_bortle),
                "elevation_m": None,
                "notes":       r["display"],
            }])
            st.success(f"Added '{site_name.strip()}'.")
            st.session_state.addr_result = None
            st.session_state.pop("addr_bortle", None)
            st.rerun()

render_sidebar()
