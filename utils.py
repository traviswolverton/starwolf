import hashlib

import requests as _req
import streamlit as st
from sqlalchemy import text
from db import get_engine, get_settings

KM_TO_MI = 0.621371


def dist_display(km: float | None, decimals: int = 0) -> str:
    """Format a distance (stored in km) using the session's unit preference."""
    if km is None:
        return "—"
    if st.session_state.get("units") == "imperial":
        return f"{km * KM_TO_MI:.{decimals}f} mi"
    return f"{km:.{decimals}f} km"


def dist_unit() -> str:
    return "mi" if st.session_state.get("units") == "imperial" else "km"


def km_to_display(km: float) -> float:
    """Convert km to the user's preferred display unit."""
    if st.session_state.get("units") == "imperial":
        return km * KM_TO_MI
    return km


def display_to_km(val: float) -> float:
    """Convert a display-unit distance back to km."""
    if st.session_state.get("units") == "imperial":
        return val / KM_TO_MI
    return val


def sync_site_active() -> None:
    """Seed/sync session_state.site_active from the DB site list.

    First visit: seeds from DB defaults.
    Subsequent renders: picks up newly imported sites, drops deleted ones,
    without resetting existing per-session choices.
    """
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT id, active FROM sites")).fetchall()
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
    "user_location", "units",
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
    if "user_location" not in st.session_state:
        st.session_state.user_location = None
    if "units" not in st.session_state:
        st.session_state.units = "metric"


def _log_visitor() -> None:
    if st.session_state.get("_visitor_logged"):
        return
    st.session_state._visitor_logged = True
    try:
        headers = st.context.headers
        ip = (
            headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or headers.get("X-Real-Ip", "")
        )
        if not ip or ip in ("127.0.0.1", "::1", ""):
            return
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()
        # Skip if we already logged this IP in the last 24 hours
        with get_engine().connect() as conn:
            seen = conn.execute(
                text("SELECT 1 FROM visitors WHERE ip_hash = :h AND visited_at > NOW() - INTERVAL '24 hours' LIMIT 1"),
                {"h": ip_hash},
            ).fetchone()
        if seen:
            return
        geo = _req.get(
            f"http://ip-api.com/json/{ip}?fields=status,city,regionName,country,countryCode,lat,lon",
            timeout=3,
        ).json()
        if geo.get("status") != "success":
            return
        with get_engine().begin() as conn:
            conn.execute(
                text("INSERT INTO visitors (ip_hash, city, region, country, country_code, lat, lon) "
                     "VALUES (:h, :city, :region, :country, :cc, :lat, :lon)"),
                {"h": ip_hash, "city": geo["city"], "region": geo["regionName"],
                 "country": geo["country"], "cc": geo["countryCode"],
                 "lat": geo["lat"], "lon": geo["lon"]},
            )
    except Exception:
        pass  # never break the app for analytics


def render_sidebar() -> None:
    """Show the user's stored location and credits at the bottom of the sidebar."""
    _log_visitor()
    st.logo("starwolf-logo.svg")
    st.markdown("""
<style>
/* Override st.logo() max-height so the logo renders at full sidebar width */
[data-testid="stLogo"] { height: auto !important; max-height: unset !important; }
[data-testid="stLogo"] img { height: auto !important; max-height: unset !important; width: 100% !important; }

@media screen and (max-width: 640px) {
    /* Reflow 4-column grids to 2×2 on mobile */
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    [data-testid="stColumn"] { min-width: 45% !important; }
    /* Tighter page padding */
    .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
    /* Prevent overflow; let tables scroll horizontally */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] { overflow-x: auto !important; }
    /* Wrap long expander labels */
    [data-testid="stExpander"] summary p { white-space: normal !important; word-break: break-word !important; }
}
</style>
""", unsafe_allow_html=True)

    loc = st.session_state.get("user_location")
    st.sidebar.divider()
    if loc:
        st.sidebar.caption("📍 **Your location**")
        st.sidebar.write(loc["display"])
        tz = st.session_state.get("timezone")
        if tz:
            st.sidebar.caption(f"🕐 {tz}")
    else:
        st.sidebar.caption("📍 No location set")
        st.sidebar.page_link("pages/0_Location.py", label="Set your location →")

    st.sidebar.divider()
    with st.sidebar.expander("🔌 API"):
        st.caption(
            "Forecast API — port **8000**  \n"
            "`GET /v1/forecast`  \n"
            "`?lat=&lon=&days=7`  \n"
            "`&bortle_class=1-9`  \n"
            "`&timezone=<IANA>`"
        )
        st.page_link(
            "http://localhost:8000/docs",
            label="Interactive docs →",
            icon="📄",
        )

    st.sidebar.divider()
    st.sidebar.caption("**Credits**")
    st.sidebar.caption(
        "**Data:** [Open-Meteo](https://open-meteo.com) · "
        "[7timer!](http://7timer.info) · "
        "[astral](https://astral.readthedocs.io) · "
        "[IDA](https://darksky.org) · "
        "[OSM](https://nominatim.org)  \n"
        "**App:** [Streamlit](https://streamlit.io) · "
        "[Claude](https://anthropic.com)  \n"
        "**By** Seth & Travis Wolverton · "
        "[Source](https://gitea.wolvertons.net/travis/stargazing-app)"
    )
