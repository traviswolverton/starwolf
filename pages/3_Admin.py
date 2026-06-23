import streamlit as st

from db import get_connection, init_db
from utils import init_session_settings, render_sidebar

import pandas as pd

init_db()
init_session_settings()

st.set_page_config(page_title="Admin — Stargazing Planner")
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

tab_weights, tab_settings = st.tabs(["Scoring Weights", "App Settings"])


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

render_sidebar()
