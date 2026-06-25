import logging
from datetime import date, datetime, timedelta

import streamlit as st
import extra_streamlit_components as stx

COOKIE_NAME = "starwolf_last_visit"
DATE_FORMAT = "%Y-%m-%d"
_SESSION_KEY = "_cookie_init_ok"

_log = logging.getLogger(__name__)


def get_cookie_manager():
    return stx.CookieManager()


def get_last_visit(cookie_manager) -> date | None:
    """Return last-visit date from cookie, or None. Sets _cookie_init_ok in session state."""
    try:
        raw = cookie_manager.get(COOKIE_NAME)
        st.session_state[_SESSION_KEY] = True
        if not raw:
            return None
        return datetime.strptime(raw, DATE_FORMAT).date()
    except Exception as e:
        st.session_state[_SESSION_KEY] = False
        _log.debug("CookieManager not yet initialized: %s", e)
        return None


def set_last_visit(cookie_manager) -> None:
    """Write today's date to the last-visit cookie (365-day expiry). No-op if manager not ready."""
    if not st.session_state.get(_SESSION_KEY, False):
        return
    try:
        expiry = datetime.now() + timedelta(days=365)
        cookie_manager.set(COOKIE_NAME, date.today().strftime(DATE_FORMAT), expires_at=expiry)
    except Exception as e:
        _log.debug("Failed to write last-visit cookie: %s", e)
