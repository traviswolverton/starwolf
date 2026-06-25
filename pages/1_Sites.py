import pandas as pd
import streamlit as st

from sqlalchemy import text
from db import get_engine, init_db
from osm_import import _haversine, find_nearest_existing, geocode, import_sites
from utils import KM_TO_MI, dist_unit, km_to_display, sync_site_active, init_session_settings, render_sidebar

init_db()
sync_site_active()
init_session_settings()

st.set_page_config(page_icon="🔭", page_title="Sites — Stargazing Planner")
st.title("Dark-Sky Sites")

if "addr_result" not in st.session_state:
    st.session_state.addr_result = None

is_imperial = st.session_state.units == "imperial"

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
st.info(
    "The **Active** column reflects your current session. "
    "Saving persists name/coordinate edits to the shared catalog and sets the default active state for new sessions.",
    icon="ℹ️",
)
sites_df = load_sites()
has_dist = "dist_km" in sites_df.columns

# Convert dist column to display units
if has_dist:
    sites_df["dist_km"] = sites_df["dist_km"].apply(
        lambda v: round(v * KM_TO_MI) if is_imperial else v
    )

col_order = ["name", "lat", "lon", "bortle_class", "elevation_m", "notes", "active"]
if has_dist:
    col_order = ["dist_km"] + col_order

col_config = {
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
    num_rows="dynamic",
    use_container_width=True,
    column_order=col_order,
    column_config=col_config,
    key="sites_editor",
)
if st.button("Save Sites"):
    save_sites(edited_sites.drop(columns=["dist_km"], errors="ignore").dropna(subset=["name"]))
    st.success("Sites saved.")


# ── Add Site by Address ────────────────────────────────────────────────────────

with st.expander("Add Site by Address"):
    addr_input = st.text_input("Address, place name, zip, or postal code", key="addr_input")

    if st.button("Look Up"):
        if not addr_input.strip():
            st.warning("Enter an address to look up.")
        else:
            try:
                with st.spinner("Looking up…"):
                    lat, lon, display = geocode(addr_input.strip())
                st.session_state.addr_result = {"lat": lat, "lon": lon, "display": display}
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

        if st.button("Add Site", type="primary", disabled=not site_name.strip()):
            import_sites([{
                "name":        site_name.strip(),
                "lat":         r["lat"],
                "lon":         r["lon"],
                "elevation_m": None,
                "notes":       r["display"],
            }])
            st.success(f"Added '{site_name.strip()}'.")
            st.session_state.addr_result = None
            st.rerun()

render_sidebar()
