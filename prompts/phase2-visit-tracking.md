# StarWolf Release Notes — Phase 2: Last-Visit Tracking & "What's New" Prompt

## Context

I'm continuing work on the StarWolf Streamlit app at `/opt/stargazing-app`.

Phase 1 is complete:
- `release_notes.json` exists with seeded entries
- `utils/release_notes.py` has `load_release_notes()`, `get_notes_since()`, and `get_notes_last_n_days()`
- The sidebar has an `st.expander("📋 Release Notes")` showing all entries

Now add last-visit tracking via browser cookie and a "What's New" prompt that appears once per session.

---

## Step 1 — Install dependency

Install `extra-streamlit-components` into the app's virtualenv:

```bash
/opt/stargazing-app/venv/bin/pip install extra-streamlit-components
```

Verify the install succeeds before proceeding.

---

## Step 2 — Create visit tracker utility

Create `/opt/stargazing-app/utils/visit_tracker.py`:

```python
import streamlit as st
from datetime import datetime, date
import extra_streamlit_components as stx

COOKIE_NAME = "starwolf_last_visit"
DATE_FORMAT = "%Y-%m-%d"

def get_cookie_manager():
    """Return a CookieManager instance. Must be called within a Streamlit render context."""
    return stx.CookieManager()

def get_last_visit(cookie_manager) -> date | None:
    """
    Read the last visit date from the browser cookie.
    Returns a date object, or None if the cookie is missing or unreadable.
    Degrades gracefully on any error.
    """

def set_last_visit(cookie_manager) -> None:
    """
    Write today's date to the last-visit cookie.
    Cookie should persist for 365 days.
    Fails silently on error.
    """
```

Implementation notes:
- Wrap all cookie reads and writes in `try/except` — CookieManager can raise or return None
  on the first render pass before the component initializes
- `get_last_visit()` should return `None` (not raise) for any failure mode
- `set_last_visit()` should use `cookie_manager.set(COOKIE_NAME, value, expires_at=...)` with
  an expiry 365 days from today

---

## Step 3 — Add "What's New" logic to app.py

In `app.py`, add the following logic. It must run **once per session** using `st.session_state`
as a guard — Streamlit reruns the full script on every interaction, so without this guard the
dialog would re-trigger on every button click.

Place this block **before** the hero section renders, near the top of the main content area.

```python
from utils.release_notes import get_notes_since, get_notes_last_n_days
from utils.visit_tracker import get_cookie_manager, get_last_visit, set_last_visit
from datetime import datetime, timedelta

# Initialize once per session
if "whats_new_shown" not in st.session_state:
    st.session_state["whats_new_shown"] = False

if not st.session_state["whats_new_shown"]:
    cookie_manager = get_cookie_manager()
    last_visit = get_last_visit(cookie_manager)

    if last_visit is not None:
        new_releases = get_notes_since(last_visit)
        heading = "✨ What's New Since Your Last Visit"
    else:
        new_releases = get_notes_last_n_days(7)
        heading = "✨ What's New in StarWolf"

    if new_releases:
        with st.container():
            st.markdown(f"### {heading}")
            for release in new_releases:
                version_str = f" — v{release['version']}" if release.get("version") else ""
                st.markdown(f"**{release['date']}{version_str}**")
                for note in release.get("notes", []):
                    st.markdown(f"- {note}")
            if st.button("Got it!", key="whats_new_dismiss"):
                set_last_visit(cookie_manager)
                st.session_state["whats_new_shown"] = True
                st.rerun()
    else:
        # No new notes — silently record visit and suppress future prompts this session
        set_last_visit(cookie_manager)
        st.session_state["whats_new_shown"] = True
```

---

## Step 4 — Guard against CookieManager double-render

`extra-streamlit-components` CookieManager renders a hidden component on first load.
On the very first script pass, cookies may not yet be readable. Add this safeguard:

- If `get_last_visit()` returns `None` due to an exception (not just a missing cookie),
  log a debug message and proceed as if no cookie exists — do not surface an error to the user
- Do NOT call `set_last_visit()` if the initial read failed with an exception (vs. simply
  returning None for a legitimately missing cookie) — distinguish these two cases in
  `visit_tracker.py` using a flag or separate exception type if needed

---

## Acceptance Criteria

- [ ] `extra-streamlit-components` installs cleanly
- [ ] `utils/visit_tracker.py` exists with both functions and full error handling
- [ ] On first-ever visit (no cookie): shows last 7 days of notes with "What's New in StarWolf" heading
- [ ] On return visit: shows only notes newer than the stored last-visit date
- [ ] "Got it!" button dismisses the prompt, records today's date, and does not re-show within the session
- [ ] If no new notes exist, the prompt is suppressed silently — no empty panel shown
- [ ] No unhandled exceptions on first render pass before CookieManager initializes
- [ ] Existing sidebar Release Notes expander from Phase 1 is unaffected
