import streamlit as st
from db import get_connection, get_settings


def sync_site_active() -> None:
    """Seed/sync session_state.site_active from the DB site list.

    First visit: seeds from DB defaults.
    Subsequent renders: picks up newly imported sites, drops deleted ones,
    without resetting existing per-session choices.
    """
    con = get_connection()
    rows = con.execute("SELECT id, active FROM sites").fetchall()
    con.close()
    db_state = {row[0]: bool(row[1]) for row in rows}
    if "site_active" not in st.session_state:
        st.session_state.site_active = db_state
    else:
        existing = st.session_state.site_active
        for site_id, active in db_state.items():
            if site_id not in existing:
                existing[site_id] = active
        st.session_state.site_active = {k: v for k, v in existing.items() if k in db_state}


_SESSION_SETTING_KEYS = [
    "timezone", "min_score_threshold",
    "disq_max_cloud_cover", "disq_max_precip_prob", "disq_min_visibility_km",
]


def init_session_settings() -> None:
    """Seed session_state user-configurable settings from DB defaults."""
    if all(k in st.session_state for k in _SESSION_SETTING_KEYS):
        return
    settings = get_settings()
    if "timezone" not in st.session_state:
        st.session_state.timezone = settings.get("timezone", "America/Chicago")
    if "min_score_threshold" not in st.session_state:
        st.session_state.min_score_threshold = int(settings.get("min_score_threshold", "40"))
    if "disq_max_cloud_cover" not in st.session_state:
        st.session_state.disq_max_cloud_cover = int(settings.get("disq_max_cloud_cover", "85"))
    if "disq_max_precip_prob" not in st.session_state:
        st.session_state.disq_max_precip_prob = int(settings.get("disq_max_precip_prob", "40"))
    if "disq_min_visibility_km" not in st.session_state:
        st.session_state.disq_min_visibility_km = int(settings.get("disq_min_visibility_km", "10"))
