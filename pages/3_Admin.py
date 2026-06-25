import os

import pandas as pd
import streamlit as st
from sqlalchemy import text

from bortle_lookup import lookup_bortle, WORLD_ATLAS_PATH
from db import get_engine, init_db
from utils import init_session_settings, render_sidebar

init_db()
init_session_settings()

st.set_page_config(page_icon="🔭", page_title="Admin — Stargazing Planner")
st.title("Admin")


# ── Password gate ──────────────────────────────────────────────────────────────

def _check_password() -> bool:
    password = st.secrets.get("admin_password") if hasattr(st.secrets, "get") else None
    if not password:
        import os
        password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        st.error(
            "Admin password not configured. "
            "Add `admin_password = \"your-password\"` to `.streamlit/secrets.toml`."
        )
        return False

    if st.session_state.get("admin_authenticated"):
        col, _ = st.columns([1, 3])
        if col.button("Log out"):
            st.session_state.admin_authenticated = False
            st.rerun()
        return True

    pwd = st.text_input("Password", type="password")
    if st.button("Log in"):
        if pwd == password:
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not _check_password():
    st.stop()


# ── Admin tabs ─────────────────────────────────────────────────────────────────

tab_weights, tab_naked_eye, tab_settings, tab_bortle = st.tabs(["Telescope Weights", "Naked Eye Weights", "App Settings", "Bortle Lookup"])


def load_weights() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(text("SELECT * FROM scoring_weights ORDER BY factor"), conn)
    return df.drop(columns=["id"])


def save_weights(df: pd.DataFrame) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM scoring_weights"))
        conn.execute(
            text("INSERT INTO scoring_weights (factor, weight, description) VALUES (:factor, :weight, :desc)"),
            [{"factor": row["factor"], "weight": row["weight"], "desc": row.get("description")}
             for _, row in df.iterrows()],
        )


with tab_weights:
    st.subheader("Telescope Weights")
    st.caption("Weights must sum to 1.00. Each factor contributes that fraction to the 0–100 telescope night quality score.")
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


def load_naked_eye_weights() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(text("SELECT * FROM naked_eye_weights ORDER BY factor"), conn)
    return df.drop(columns=["id"])


def save_naked_eye_weights(df: pd.DataFrame) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM naked_eye_weights"))
        conn.execute(
            text("INSERT INTO naked_eye_weights (factor, weight, description) VALUES (:factor, :weight, :desc)"),
            [{"factor": row["factor"], "weight": row["weight"], "desc": row.get("description")}
             for _, row in df.iterrows()],
        )


with tab_naked_eye:
    st.subheader("Naked Eye Weights")
    st.caption(
        "Weights must sum to 1.00. "
        "Seeing stability matters less for naked eye; moon and cloud cover dominate. "
        "A Bortle penalty (separate from these weights) is also applied based on each site's light pollution."
    )
    naked_eye_df = load_naked_eye_weights()
    edited_naked_eye = st.data_editor(
        naked_eye_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "factor":      st.column_config.TextColumn("Factor", required=True),
            "weight":      st.column_config.NumberColumn("Weight", min_value=0.0, max_value=1.0, format="%.2f", required=True),
            "description": st.column_config.TextColumn("Description", width="large"),
        },
        key="naked_eye_weights_editor",
    )
    ne_total = edited_naked_eye["weight"].sum()
    if abs(ne_total - 1.0) > 0.001:
        st.warning(f"Weights sum to **{ne_total:.3f}** — must equal 1.00 before saving.")
    else:
        st.success(f"Weights sum to **{ne_total:.2f}**")
    if st.button("Save Naked Eye Weights", disabled=(abs(ne_total - 1.0) > 0.001)):
        save_naked_eye_weights(edited_naked_eye.dropna(subset=["factor"]))
        st.success("Naked eye weights saved.")


def load_settings() -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text("SELECT * FROM app_settings ORDER BY key"), conn)


def save_settings(df: pd.DataFrame) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM app_settings"))
        conn.execute(
            text("INSERT INTO app_settings (key, value, description) VALUES (:key, :value, :desc)"),
            [{"key": row["key"], "value": row["value"], "desc": row.get("description")}
             for _, row in df.iterrows()],
        )


with tab_settings:
    st.subheader("App Settings")
    st.caption(
        "`forecast_days` controls the forecast horizon (admin only). "
        "`timezone` and `min_score_threshold` are session defaults — users can override them in Preferences."
    )
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

with tab_bortle:
    st.subheader("Batch Bortle Lookup")
    st.caption(
        "Fills in Bortle class for all sites that currently have none, "
        "using the World Atlas of Artificial Night Sky Brightness (Falchi et al. 2016)."
    )

    atlas_present = os.path.exists(WORLD_ATLAS_PATH)
    if not atlas_present:
        st.error(
            f"GeoTIFF not found at `{WORLD_ATLAS_PATH}`.  \n"
            "Run `scripts/download_world_atlas.sh` to download it (~2.9 GB, one-time)."
        )
    else:
        st.success(f"GeoTIFF present: `{WORLD_ATLAS_PATH}`")

    with get_engine().connect() as conn:
        null_sites = conn.execute(
            text("SELECT id, name, lat, lon FROM sites WHERE bortle_class IS NULL ORDER BY name")
        ).fetchall()

    st.metric("Sites missing Bortle", len(null_sites))

    if null_sites:
        with st.expander(f"Sites without Bortle ({len(null_sites)})", expanded=False):
            st.dataframe(
                pd.DataFrame(null_sites, columns=["id", "name", "lat", "lon"]).drop(columns=["id"]),
                use_container_width=True,
                hide_index=True,
            )

    if st.button("Fill Bortle for all null sites", type="primary", disabled=not atlas_present or not null_sites):
        progress = st.progress(0, text="Looking up…")
        ok, failed = 0, []
        for i, (site_id, name, lat, lon) in enumerate(null_sites):
            try:
                result = lookup_bortle(lat, lon)
                with get_engine().begin() as conn:
                    conn.execute(
                        text("UPDATE sites SET bortle_class = :b WHERE id = :id"),
                        {"b": result["bortle"], "id": site_id},
                    )
                ok += 1
            except Exception as e:
                failed.append(f"{name}: {e}")
            progress.progress((i + 1) / len(null_sites), text=f"{name}…")
        progress.empty()
        if ok:
            st.success(f"Updated {ok} site(s).")
        if failed:
            st.warning("Some lookups failed:\n" + "\n".join(f"- {f}" for f in failed))
        st.rerun()


render_sidebar()
