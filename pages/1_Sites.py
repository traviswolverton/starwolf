import pandas as pd
import streamlit as st

from db import get_connection, init_db
from osm_import import _haversine, find_nearest_existing, geocode, import_sites, search_dark_sky_sites
from utils import KM_TO_MI, dist_unit, km_to_display, sync_site_active, init_session_settings, render_sidebar

init_db()
sync_site_active()
init_session_settings()

st.set_page_config(page_title="Sites — Stargazing Planner")
st.title("Dark-Sky Sites")

if "osm_results" not in st.session_state:
    st.session_state.osm_results = None
if "osm_origin" not in st.session_state:
    st.session_state.osm_origin = None
if "addr_result" not in st.session_state:
    st.session_state.addr_result = None

is_imperial = st.session_state.units == "imperial"

# ── Activate by proximity ──────────────────────────────────────────────────────

with st.expander("Activate by proximity"):
    # Pre-fill from stored user location if the widget hasn't been touched yet
    if "prox_location" not in st.session_state and st.session_state.user_location:
        st.session_state.prox_location = st.session_state.user_location["text"]

    prox_location = st.text_input("Location, zip, or postal code", key="prox_location")

    if is_imperial:
        prox_radius_display = st.slider("Radius (mi)", min_value=6, max_value=3000, value=300, step=10)
        prox_radius_km = prox_radius_display / KM_TO_MI
    else:
        prox_radius_km = st.slider("Radius (km)", min_value=10, max_value=5000, value=500, step=10)
        prox_radius_display = prox_radius_km

    if st.button("Activate Sites in Range"):
        if not prox_location.strip():
            st.warning("Enter a location.")
        else:
            try:
                with st.spinner("Updating…"):
                    lat, lon, display = geocode(prox_location.strip())
                    con = get_connection()
                    all_sites = con.execute("SELECT id, name, lat, lon FROM sites").fetchall()
                    con.close()
                    new_active = dict(st.session_state.site_active)
                    for site_id, name, slat, slon in all_sites:
                        new_active[site_id] = _haversine(lat, lon, slat, slon) <= prox_radius_km
                    st.session_state.site_active = new_active
                # Save as user location if none is set yet
                if not st.session_state.user_location:
                    st.session_state.user_location = {"text": prox_location.strip(), "lat": lat, "lon": lon, "display": display}
                activated = sum(1 for site_id, _, slat, slon in all_sites if new_active[site_id])
                unit = dist_unit()
                st.success(f"Activated {activated} site(s) within {prox_radius_display:.0f} {unit} of {display.split(',')[0]}.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
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
    con = get_connection()
    df = pd.read_sql("SELECT * FROM sites ORDER BY name", con)
    con.close()
    active = st.session_state.site_active
    df["active"] = df["id"].map(lambda i: active.get(i, True)).astype(bool)
    loc = st.session_state.get("user_location")
    if loc:
        df["dist_km"] = df.apply(
            lambda r: round(_haversine(loc["lat"], loc["lon"], r["lat"], r["lon"])), axis=1
        )
    return df


def save_sites(df: pd.DataFrame) -> None:
    con = get_connection()
    cur = con.cursor()
    cur.execute("DELETE FROM sites")
    for _, row in df.iterrows():
        cur.execute(
            "INSERT INTO sites (name, lat, lon, bortle_class, elevation_m, notes, active) VALUES (?,?,?,?,?,?,?)",
            (row["name"], row["lat"], row["lon"], row.get("bortle_class"),
             row.get("elevation_m"), row.get("notes"), int(row["active"])),
        )
    con.commit()
    rows = con.execute("SELECT id, active FROM sites").fetchall()
    st.session_state.site_active = {row[0]: bool(row[1]) for row in rows}
    con.close()


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


# ── Import IDA Dark Sky Sites ──────────────────────────────────────────────────

st.divider()
with st.expander("Import IDA Dark Sky Sites"):
    location_input = st.text_input("Location, zip code, or postal code", key="osm_location")

    if is_imperial:
        ida_radius_display = st.slider("Search radius (mi)", min_value=6, max_value=620, value=60, step=10)
        ida_radius_km = round(ida_radius_display / KM_TO_MI)
    else:
        ida_radius_km = st.slider("Search radius (km)", min_value=10, max_value=1000, value=100, step=10)
        ida_radius_display = ida_radius_km

    if st.button("Find Dark Sky Sites"):
        if not location_input.strip():
            st.warning("Enter a location to search.")
        else:
            try:
                with st.spinner("Searching…"):
                    lat, lon, display = geocode(location_input.strip())
                    results = search_dark_sky_sites(lat, lon, ida_radius_km)
                st.session_state.osm_origin = (lat, lon, display)
                st.session_state.osm_results = results
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Search failed: {e}")

    if st.session_state.osm_results is not None:
        _, _, display = st.session_state.osm_origin
        st.caption(f"Results near: {display}")

        results = st.session_state.osm_results
        if not results:
            st.info("No dark-sky sites found in that area. Try a larger radius.")
        else:
            to_import = []
            for i, site in enumerate(results):
                dup = find_nearest_existing(site["lat"], site["lon"])
                dist_val = site["distance_km"]
                dist_str = f"{round(dist_val * KM_TO_MI)} mi" if is_imperial else f"{dist_val} km"
                label = f"**{site['name']}** — {dist_str} away"
                checked = st.checkbox(label, value=(dup is None), key=f"osm_{i}")
                if dup:
                    dup_dist = f"{round(dup[1] * KM_TO_MI)} mi" if is_imperial else f"{dup[1]} km"
                    st.caption(f"  ⚠️ Possible duplicate: {dup[0]} ({dup_dist} away in DB)")
                if checked:
                    to_import.append(site)

            if st.button("Import Selected", type="primary", disabled=not to_import):
                n = import_sites(to_import)
                st.success(f"Imported {n} site(s).")
                st.session_state.osm_results = None
                st.session_state.osm_origin = None
                st.rerun()


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
