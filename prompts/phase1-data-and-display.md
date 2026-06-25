# StarWolf Release Notes — Phase 1: Data Format & Display UI

## Context

I'm working on a Streamlit app called StarWolf (a stargazing planner) located at `/opt/stargazing-app`.
The app entry point is `app.py`. Dependencies are managed via `/opt/stargazing-app/venv`.
The app displays stargazing forecasts for dark-sky sites across Texas, scoring conditions by cloud cover,
moon phase, humidity, atmospheric seeing, and transparency. Each result card shows both a telescope
score (🔭) and a naked eye score (👁).

---

## Task

Create a release notes system — data file, utility functions, and sidebar display. No visit-tracking yet.

---

## Style Guide

When writing release note bullets, use plain conversational language as if explaining to a friend who
loves stargazing but doesn't write code. Lead each bullet with a verb. Focus on what the user can now
*do* or *see* differently, not what changed technically. Avoid words like "refactored", "endpoint",
"component", "parameter", or "API". Prefer specificity over vagueness — "Moon score now weighs more
heavily for naked eye viewing" beats "Improved scoring logic". Keep bullets to one sentence. If a
change only affects the backend with no visible user impact, omit it.

---

## Step 1 — Create the release notes data file

Create `/opt/stargazing-app/release_notes.json` with this structure:

```json
{
  "releases": [
    {
      "date": "YYYY-MM-DD",
      "version": "X.Y.Z",
      "notes": [
        "User-facing bullet one.",
        "User-facing bullet two."
      ]
    }
  ]
}
```

Seed it with three entries using the style guide above. Use today's date for the most recent entry.
Base the entries on these real changes that have shipped in StarWolf:

- Added a naked eye score (👁) alongside the existing telescope score (🔭) on every result card
- Sort options expanded: users can now sort by naked eye score, telescope score, date, or location
- Landing page redesigned: hero button moved to top, collapsible "How It Works" and "Reading Your Results" sections added via expanders
- SVG logo finalized: features a white star, rolling Texas hills, a green telescope, and the StarWolf wordmark with "STARGAZING PLANNER" tagline
- Feedback pipeline added: users can report issues directly to the development team

Assign plausible version numbers (start at 1.0.0 and increment reasonably across the three entries).
Newest entry goes first in the array.

---

## Step 2 — Create utility functions

Create `/opt/stargazing-app/utils/release_notes.py` with these three functions:

```python
def load_release_notes() -> dict:
    """Read and return the full release_notes.json contents."""

def get_notes_since(since_date: datetime) -> list:
    """Return all release entries with a date strictly after since_date. Newest first."""

def get_notes_last_n_days(n: int) -> list:
    """Return all release entries from the last N days. Newest first."""
```

- Parse dates using `datetime.strptime(entry["date"], "%Y-%m-%d").date()`
- Return a list of release entry dicts (same shape as the JSON objects)
- If the file is missing or malformed, log a warning and return an empty list — do not raise

---

## Step 3 — Add sidebar display in app.py

In `app.py`, add a release notes expander to the sidebar. Place it near the bottom of the sidebar,
below any existing controls.

```python
with st.sidebar:
    # ... existing sidebar content ...
    with st.expander("📋 Release Notes", expanded=False):
        releases = load_release_notes().get("releases", [])
        if not releases:
            st.caption("No release notes available.")
        for release in releases:
            version_str = f" — v{release['version']}" if release.get("version") else ""
            st.markdown(f"**{release['date']}{version_str}**")
            for note in release.get("notes", []):
                st.markdown(f"- {note}")
```

Style notes:
- Keep it simple — no custom CSS needed at this stage
- Newest release shows first (already guaranteed by data order)
- The expander should be collapsed by default

---

## Acceptance Criteria

- [ ] `release_notes.json` exists with 3 seeded entries, newest first
- [ ] `utils/release_notes.py` exists with all three functions and graceful error handling
- [ ] Sidebar expander renders all entries correctly in the running app
- [ ] No errors on first load if `release_notes.json` is missing (degrades silently)
