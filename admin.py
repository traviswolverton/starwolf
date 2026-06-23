from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_connection, init_db

init_db()

st.set_page_config(page_title="Stargazing Planner", layout="wide")

col_logo, col_about = st.columns([1, 2])
with col_logo:
    st.image("starwolf-logo.svg", width=300)
with col_about:
    st.markdown("""
### Stargazing Trip Planner
Plan optimal stargazing nights at dark-sky sites across North America. Enter your sites, pull live
forecasts, and get a composite night-quality score so you can pick the best window for your trip.

**Data sources & credits**
| | |
|---|---|
| **Weather & atmosphere** | [Open-Meteo](https://open-meteo.com) — free, no API key, 16-day hourly forecast |
| **Astronomical seeing** | [7timer!](http://www.7timer.info) — purpose-built for astronomers |
| **Moon phase / rise / set** | `astral` Python library — fully offline |
| **Dark sky site data** | [IDA / DarkSky International](https://darksky.org) — designated places dataset |
| **Geocoding** | [Nominatim / OpenStreetMap](https://nominatim.org) & [Natural Resources Canada](https://geogratis.gc.ca) |
| **App** | Built with [Streamlit](https://streamlit.io) · AI assistance by [Claude](https://anthropic.com) |
| **Authors** | Seth & Travis Wolverton |
| **Source** | [gitea.wolvertons.net/travis/stargazing-app](https://gitea.wolvertons.net/travis/stargazing-app) |
""")

if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "nights" not in st.session_state:
    st.session_state.nights = None
if "osm_results" not in st.session_state:
    st.session_state.osm_results = None
if "osm_origin" not in st.session_state:
    st.session_state.osm_origin = None
if "addr_result" not in st.session_state:
    st.session_state.addr_result = None


def _load_active_sites() -> list[dict]:
    con = get_connection()
    sites = pd.read_sql("SELECT * FROM sites WHERE active = 1 ORDER BY name", con).to_dict("records")
    con.close()
    return sites


def _fetch_and_score() -> list:
    from forecast import fetch_site_forecast
    from scorer import score_all
    sites = _load_active_sites()
    return score_all([fetch_site_forecast(s) for s in sites])


def _nights_to_df(nights: list) -> pd.DataFrame:
    rows = []
    for n in nights:
        f = n["factors"]
        s = n["stats"]
        rows.append({
            "Date":         datetime.fromisoformat(n["date"]).strftime("%a %-d %b"),
            "Site":         n["site"],
            "Score":        n["composite"],
            "Dark Hrs":     s["night_hours"],
            "Cloud %":      s["avg_cloud_cover"],
            "Hi Cloud %":   s["avg_high_cloud"],
            "Moon":         f["moon"],
            "Lifted Index": s["avg_lifted_index"],
            "Humidity %":   s["avg_humidity"],
            "Seeing (7T)":  s["seeing_7timer"],
        })
    return pd.DataFrame(rows)


# ── Site selection / results ───────────────────────────────────────────────────

if not st.session_state.show_results:
    active_sites = _load_active_sites()
    if active_sites:
        st.caption(f"{len(active_sites)} active site(s) — manage in the Dark-Sky Sites tab.")

    with st.expander("Activate sites by proximity"):
        from osm_import import geocode, _haversine
        from db import get_connection

        prox_location = st.text_input("Location, zip, or postal code", key="prox_location")
        prox_radius   = st.slider("Radius (km)", min_value=10, max_value=5000, value=500, step=10, key="prox_radius")

        if st.button("Activate Sites in Range"):
            if not prox_location.strip():
                st.warning("Enter a location.")
            else:
                try:
                    with st.spinner("Updating…"):
                        lat, lon, display = geocode(prox_location.strip())
                        con = get_connection()
                        all_sites = con.execute("SELECT id, name, lat, lon FROM sites").fetchall()
                        for site_id, name, slat, slon in all_sites:
                            in_range = _haversine(lat, lon, slat, slon) <= prox_radius
                            con.execute("UPDATE sites SET active = ? WHERE id = ?", (1 if in_range else 0, site_id))
                        con.commit()
                        con.close()
                    activated = sum(1 for _, _, slat, slon in all_sites if _haversine(lat, lon, slat, slon) <= prox_radius)
                    st.success(f"Activated {activated} site(s) within {prox_radius} km of {display.split(',')[0]}.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Failed: {e}")

    col_activate, col_deactivate, col_forecast = st.columns([1, 1, 1])
    with col_activate:
        if st.button("Activate All Sites", use_container_width=True):
            con = get_connection()
            con.execute("UPDATE sites SET active = 1")
            con.commit()
            con.close()
            st.rerun()
    with col_deactivate:
        if st.button("Deactivate All Sites", use_container_width=True):
            con = get_connection()
            con.execute("UPDATE sites SET active = 0")
            con.commit()
            con.close()
            st.rerun()
    with col_forecast:
        if st.button("Run Forecast", type="primary", use_container_width=True, disabled=not active_sites):
            with st.spinner("Fetching forecasts…"):
                st.session_state.nights = _fetch_and_score()
            st.session_state.show_results = True
            st.rerun()

else:
    if st.button("← Back"):
        st.session_state.show_results = False
        st.rerun()

    nights = st.session_state.nights

    if not nights:
        st.warning("No forecast data returned. Check that sites are active and APIs are reachable.")
    else:
        # ── Ranked table ──────────────────────────────────────────────────────
        st.subheader("Best Nights")
        st.caption("All scores and averages are calculated using nighttime hours only (when is\\_day = 0 at the site's location), so daytime weather never affects your results.")
        ranked = sorted(nights, key=lambda n: -n["composite"])
        st.dataframe(
            _nights_to_df(ranked),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Dark Hrs":     st.column_config.NumberColumn("Dark Hrs", format="%d hrs",
                                    help="Number of nighttime hours used to compute this score. Shorter nights (summer) will have fewer hours."),
                "Score":        st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f",
                                    help="Composite night quality score (0–100). Above 70 is worth the drive; below 40 is likely a bust."),
                "Cloud %":      st.column_config.NumberColumn(format="%.0f%%",
                                    help="Average total cloud cover during nighttime hours. Under 20% is ideal; above 50% is likely a washout."),
                "Hi Cloud %":   st.column_config.NumberColumn(format="%.0f%%",
                                    help="Average high cirrus cloud cover (20,000+ ft). Even thin cirrus kills transparency — watch this even when total cloud cover looks OK."),
                "Moon":         st.column_config.NumberColumn(format="%.0f",
                                    help="Moon factor score (0–100). Accounts for illumination percentage and hours above the horizon. Higher is better (darker sky)."),
                "Lifted Index": st.column_config.NumberColumn(format="%.1f",
                                    help="Atmospheric stability proxy for seeing quality. Positive = stable air = steady stars. Aim for > +3. Negative values mean turbulent air and boiling images."),
                "Humidity %":   st.column_config.NumberColumn(format="%.0f%%",
                                    help="Average relative humidity during nighttime hours. Above 85% risks dew on eyepieces and corrector plates. Bring a dew heater above 75%."),
                "Seeing (7T)":  st.column_config.NumberColumn(format="%.1f",
                                    help="Astronomical seeing from 7timer! (1–8 scale, higher is better). Predicts star steadiness for high-magnification work. Only available within ~8 days; blank beyond that."),
            },
        )

        # ── Calendar heatmap ──────────────────────────────────────────────────
        st.subheader("Night Quality Heatmap")
        pivot = (
            pd.DataFrame([{"site": n["site"], "date": n["date"], "score": n["composite"]} for n in nights])
            .pivot_table(index="site", columns="date", values="score", aggfunc="first")
        )
        pivot.columns = [datetime.fromisoformat(d).strftime("%a %-d %b") for d in pivot.columns]

        fig = px.imshow(
            pivot,
            color_continuous_scale="RdYlGn",
            zmin=0,
            zmax=100,
            aspect="auto",
            labels={"color": "Score", "x": "", "y": ""},
        )
        fig.update_layout(
            coloraxis_colorbar=dict(title="Score", tickvals=[0, 25, 50, 75, 100]),
            margin=dict(l=0, r=0, t=40, b=0),
            xaxis=dict(side="top"),
        )
        fig.update_traces(
            hovertemplate="<b>%{y}</b><br>%{x}<br>Score: %{z:.1f}<extra></extra>"
        )
        st.plotly_chart(fig, use_container_width=True)


# ── Admin tabs ─────────────────────────────────────────────────────────────────

st.divider()
tab_sites, tab_weights, tab_settings = st.tabs(["Dark-Sky Sites", "Scoring Weights", "App Settings"])


def load_sites() -> pd.DataFrame:
    con = get_connection()
    df = pd.read_sql("SELECT * FROM sites ORDER BY name", con)
    con.close()
    df["active"] = df["active"].astype(bool)
    return df.drop(columns=["id"])


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
    con.close()


with tab_sites:
    st.info(
        "**Two ways to add sites:**\n\n"
        "- **Search below** to find IDA-designated dark sky sites near any location and import them in one click.\n"
        "- **Edit the table directly** to add, modify, or deactivate any site manually.",
        icon="🌌",
    )
    st.subheader("Dark-Sky Sites")
    sites_df = load_sites()
    edited_sites = st.data_editor(
        sites_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name":         st.column_config.TextColumn("Name", required=True),
            "lat":          st.column_config.NumberColumn("Latitude",  format="%.4f", min_value=-90,  max_value=90),
            "lon":          st.column_config.NumberColumn("Longitude", format="%.4f", min_value=-180, max_value=180),
            "bortle_class": st.column_config.NumberColumn("Bortle Class", min_value=1, max_value=9, step=1),
            "elevation_m":  st.column_config.NumberColumn("Elevation (m)"),
            "notes":        st.column_config.TextColumn("Notes", width="large"),
            "active":       st.column_config.CheckboxColumn("Active"),
        },
        key="sites_editor",
    )
    if st.button("Save Sites"):
        save_sites(edited_sites.dropna(subset=["name"]))
        st.success("Sites saved.")

    st.divider()
    with st.expander("Import IDA Dark Sky Sites"):
        from osm_import import geocode, search_dark_sky_sites, find_nearest_existing, import_sites

        location_input = st.text_input("Location, zip code, or postal code", key="osm_location")
        radius = st.slider("Search radius (km)", min_value=10, max_value=1000, value=100, step=10)

        if st.button("Find Dark Sky Sites"):
            if not location_input.strip():
                st.warning("Enter a location to search.")
            else:
                try:
                    with st.spinner("Searching…"):
                        lat, lon, display = geocode(location_input.strip())
                        results = search_dark_sky_sites(lat, lon, radius)
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
                    label = f"**{site['name']}** — {site['distance_km']} km away"
                    checked = st.checkbox(label, value=(dup is None), key=f"osm_{i}")
                    if dup:
                        st.caption(f"  ⚠️ Possible duplicate: {dup[0]} ({dup[1]} km away in DB)")
                    if checked:
                        to_import.append(site)

                if st.button("Import Selected", type="primary", disabled=not to_import):
                    n = import_sites(to_import)
                    st.success(f"Imported {n} site(s).")
                    st.session_state.osm_results = None
                    st.session_state.osm_origin = None
                    st.rerun()

    with st.expander("Add Site by Address"):
        from osm_import import geocode, find_nearest_existing, import_sites

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
                st.warning(f"⚠️ Possible duplicate: {dup[0]} ({dup[1]} km away in DB)")

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


def load_weights() -> pd.DataFrame:
    con = get_connection()
    df = pd.read_sql("SELECT * FROM scoring_weights ORDER BY factor", con)
    con.close()
    return df.drop(columns=["id"])


def save_weights(df: pd.DataFrame) -> None:
    con = get_connection()
    cur = con.cursor()
    cur.execute("DELETE FROM scoring_weights")
    for _, row in df.iterrows():
        cur.execute(
            "INSERT INTO scoring_weights (factor, weight, description) VALUES (?,?,?)",
            (row["factor"], row["weight"], row.get("description")),
        )
    con.commit()
    con.close()


with tab_weights:
    st.subheader("Scoring Weights")
    st.caption("Weights must sum to 1.00. Each factor contributes that fraction to the 0–100 night quality score.")
    weights_df = load_weights()
    edited_weights = st.data_editor(
        weights_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "factor":      st.column_config.TextColumn("Factor", required=True),
            "weight":      st.column_config.NumberColumn("Weight", min_value=0.0, max_value=1.0, format="%.2f", required=True),
            "description": st.column_config.TextColumn("Description", width="large"),
        },
        key="weights_editor",
    )
    total = edited_weights["weight"].sum()
    if abs(total - 1.0) > 0.001:
        st.warning(f"Weights sum to **{total:.3f}** — must equal 1.00 before saving.")
    else:
        st.success(f"Weights sum to **{total:.2f}**")
    if st.button("Save Weights", disabled=(abs(total - 1.0) > 0.001)):
        save_weights(edited_weights.dropna(subset=["factor"]))
        st.success("Weights saved.")


def load_settings() -> pd.DataFrame:
    con = get_connection()
    df = pd.read_sql("SELECT * FROM app_settings ORDER BY key", con)
    con.close()
    return df


def save_settings(df: pd.DataFrame) -> None:
    con = get_connection()
    cur = con.cursor()
    cur.execute("DELETE FROM app_settings")
    for _, row in df.iterrows():
        cur.execute(
            "INSERT INTO app_settings (key, value, description) VALUES (?,?,?)",
            (row["key"], row["value"], row.get("description")),
        )
    con.commit()
    con.close()


with tab_settings:
    st.subheader("App Settings")
    settings_df = load_settings()
    edited_settings = st.data_editor(
        settings_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "key":         st.column_config.TextColumn("Key", required=True),
            "value":       st.column_config.TextColumn("Value", required=True),
            "description": st.column_config.TextColumn("Description", width="large"),
        },
        key="settings_editor",
    )
    if st.button("Save Settings"):
        save_settings(edited_settings.dropna(subset=["key"]))
        st.success("Settings saved.")
