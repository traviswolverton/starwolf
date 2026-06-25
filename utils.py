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
    "user_location", "units", "planner_radius_km",
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
    if "planner_radius_km" not in st.session_state:
        st.session_state.planner_radius_km = int(settings.get("default_radius_km", "500"))


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
    import streamlit.components.v1 as _components
    _log_visitor()
    st.logo("starwolf-logo.svg")
    st.markdown("""
<style>
/* Override st.logo() max-height so the logo renders at full sidebar width */
[data-testid="stLogo"] { height: auto !important; max-height: unset !important; }
[data-testid="stLogo"] img { height: auto !important; max-height: unset !important; width: 100% !important; }

/* ── Mobile sidebar toggle ───────────────────────────────────────────────── */
@media screen and (max-width: 640px) {
    [data-testid="stExpandSidebarButton"] {
        background: rgba(0, 180, 100, 0.25) !important;
        border: 1px solid rgba(0, 180, 100, 0.6) !important;
        border-radius: 0 8px 8px 0 !important;
        animation: sidebar-pulse 2.5s ease-in-out infinite !important;
    }
    @keyframes sidebar-pulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(0, 180, 100, 0.4); }
        50%       { box-shadow: 0 0 0 6px rgba(0, 180, 100, 0); }
    }
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

    # Inject GitHub button into parent DOM — st.markdown strips <a> tags,
    # so we use a 0-height component iframe that writes to window.parent.document.
    _components.html("""
<script>
(function() {
    var doc = window.parent.document;
    if (doc.getElementById('gh-link')) return;
    var a = doc.createElement('a');
    a.id = 'gh-link';
    a.href = 'https://github.com/traviswolverton/starwolf';
    a.target = '_blank';
    a.title = 'View source on GitHub';
    a.style.cssText = 'position:fixed;bottom:1.2rem;right:1.2rem;z-index:9999;'
        + 'background:#24292e;border-radius:50%;width:2.4rem;height:2.4rem;'
        + 'display:flex;align-items:center;justify-content:center;'
        + 'box-shadow:0 2px 8px rgba(0,0,0,0.5);opacity:0.85;'
        + 'transition:opacity 0.2s,transform 0.2s;text-decoration:none;';
    a.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="white">'
        + '<path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57'
        + ' 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41'
        + '-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815'
        + ' 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925'
        + ' 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23'
        + ' .96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65'
        + ' .24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925'
        + ' .435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57'
        + ' A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>';
    a.onmouseover = function() { this.style.opacity='1'; this.style.transform='scale(1.1)'; };
    a.onmouseout  = function() { this.style.opacity='0.85'; this.style.transform='scale(1)'; };
    doc.body.appendChild(a);
})();
</script>
""", height=0)

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

    # Initialize toggle on first render
    if "_sidebar_units_sel" not in st.session_state:
        st.session_state["_sidebar_units_sel"] = "Imperial" if st.session_state.get("units") == "imperial" else "Metric"
    # Sync toggle when units was changed externally (e.g. Preferences page).
    # _toggle_units_set tracks what the toggle itself last wrote, so we only
    # override when a different source changed units — not when the toggle did.
    _toggle_set = st.session_state.get("_toggle_units_set")
    _curr_units = st.session_state.get("units", "metric")
    if _toggle_set is not None and _curr_units != _toggle_set:
        st.session_state["_sidebar_units_sel"] = "Imperial" if _curr_units == "imperial" else "Metric"

    _units_sel = st.sidebar.segmented_control(
        "Units", options=["Metric", "Imperial"], key="_sidebar_units_sel"
    )
    if _units_sel:
        st.session_state.units = "imperial" if _units_sel == "Imperial" else "metric"
        st.session_state["_toggle_units_set"] = st.session_state.units

    st.sidebar.divider()
    with st.sidebar.expander("📋 Release Notes", expanded=False):
        from release_notes import load_release_notes
        releases = load_release_notes().get("releases", [])
        if not releases:
            st.caption("No release notes available.")
        for release in releases:
            version_str = f" — v{release['version']}" if release.get("version") else ""
            st.markdown(f"**{release['date']}{version_str}**")
            if release.get("features"):
                st.markdown("*Features*")
                for note in release["features"]:
                    st.markdown(f"- {note}")
            if release.get("fixes"):
                st.markdown("*Bug Fixes*")
                for note in release["fixes"]:
                    st.markdown(f"- {note}")

    st.sidebar.divider()
    st.sidebar.caption("**Credits**")
    st.sidebar.caption(
        "**Data:** [Open-Meteo](https://open-meteo.com) · "
        "[7timer!](http://7timer.info) · "
        "[astral](https://astral.readthedocs.io) · "
        "[IDA](https://darksky.org) · "
        "[OSM](https://nominatim.org) · "
        "[Falchi et al. 2016](https://doi.org/10.5880/GFZ.1.4.2016.001)  \n"
        "**App:** [Streamlit](https://streamlit.io) · "
        "[Claude](https://anthropic.com)  \n"
        "**By** Seth & Travis Wolverton · "
        "[Source](https://github.com/traviswolverton/starwolf)"
    )
