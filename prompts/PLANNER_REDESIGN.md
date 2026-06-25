# Planner.py — Pre-Forecast Layout Refactor

Refactor the pre-forecast landing section of `Planner.py`. The goal is to replace the current "wall of text + warning + button" layout with a clean dashboard-style landing that feels purposeful rather than instructional.

**Scope:** Change only the `if not st.session_state.show_results:` block. The `else:` block (results section) is not to be touched.

---

## Structure to build

Replace the existing pre-forecast block with the following, in this order:

### 1. Hero button — first thing on the page

- Move the Run Forecast button to the top, before any other content
- `type="primary"`, `use_container_width=True`
- Keep existing `disabled=not active_sites` logic
- Below the button, show a single `st.caption`:
  ```
  f"{len(active_sites)} of {total_sites} sites active · {st.session_state.timezone}"
  ```
- Remove the `st.warning` for missing location entirely — do not replace it with anything
- Remove the `st.spinner` from the button callback; it is not needed here

### 2. Setup status row — three columns below the button

Use `st.columns(3)`. Each column uses `st.container(border=True)` and contains: a status emoji, a bold step label, a one-line status caption, and a `st.page_link` where noted.

| Column | Condition | Emoji | Caption | Link |
|---|---|---|---|---|
| **Location** | `st.session_state.user_location` is set | ✅ | `loc["display"]` | — |
| **Location** | not set | ⚙️ | `"Not set"` | `st.page_link("pages/0_Location.py", label="Set location →")` |
| **Sites** | `len(active_sites) > 0` | ✅ | `f"{len(active_sites)} of {total_sites} active"` | `st.page_link("pages/1_Sites.py", label="Manage sites →")` |
| **Sites** | none active | ⚙️ | `"No sites active"` | `st.page_link("pages/1_Sites.py", label="Manage sites →")` |
| **Preferences** | always | ✅ | `f"Threshold {st.session_state.min_score_threshold} · {st.session_state.timezone}"` | `st.page_link("pages/2_Preferences.py", label="Adjust →")` |

### 3. "How it works" — collapsible, collapsed by default

Wrap the existing How it works `st.markdown` content in:
```python
with st.expander("How it works", expanded=False):
```
Keep the markdown content exactly as-is. Remove the `st.divider()` that currently precedes this block.

### 4. "Reading your results" — separate collapsible, collapsed by default

Split the existing markdown at the `### Reading your results` heading into its own expander:
```python
with st.expander("Reading your results", expanded=False):
```
These should be two separate expanders, not nested.

---

## Constraints

- Do not change any imports
- Do not change any helper functions: `_load_active_sites`, `_fetch_and_score`, `_score_color`, `_fmt`, `_norm`, `_colored_metric`
- Do not change the `else:` results block
- Do not change the `render_sidebar()` call at the bottom
- Keep `st.title("Stargazing Trip Planner")` in place
- Preserve all existing session state logic — only the UI layout changes
