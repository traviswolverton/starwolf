# Add Naked Eye Score to Results

Add a second composite score — **naked eye** — alongside the existing telescope score on every night result. No mode toggle; both scores are always visible. The sort options expand to include both score types.

---

## 1. `scorer.py` — add naked eye scoring

### 1a. Add `NAKED_EYE_WEIGHTS` constant

Add this constant near the top of the file, after the existing per-factor scorer functions:

```python
# Naked eye viewing weights — Bortle-adjusted, seeing irrelevant
NAKED_EYE_WEIGHTS = {
    "cloud_cover":  0.40,
    "moon":         0.35,
    "high_cloud":   0.10,
    "humidity":     0.10,
    "lifted_index": 0.05,   # atmospheric stability still marginally relevant
}
```

Seeing and transparency are excluded entirely — they are telescope-only concerns.

### 1b. Add Bortle modifier

Add this function after `_score_humidity`:

```python
def _bortle_naked_eye_modifier(bortle_class: int | None) -> float:
    """
    Returns a multiplier (0.7–1.0) applied to the naked eye composite.
    Bortle 1–2 → no penalty; Bortle 3–4 → mild; Bortle 5–6 → moderate; Bortle 7+ → heavy.
    Returns 1.0 if bortle_class is None (unknown site).
    """
    if bortle_class is None:
        return 1.0
    modifiers = {1: 1.0, 2: 1.0, 3: 0.92, 4: 0.84, 5: 0.75, 6: 0.70, 7: 0.65, 8: 0.60, 9: 0.55}
    return modifiers.get(bortle_class, 1.0)
```

### 1c. Update `score_forecast` signature and logic

Update the signature to accept site Bortle class:

```python
def score_forecast(forecast: dict, tz_str: str, disqualifiers: dict | None = None) -> list:
```

The `forecast["site"]` dict already contains all site fields from the DB query. Access Bortle with:

```python
bortle = site.get("bortle_class")  # may be None
```

After computing `factor_scores`, add the naked eye composite calculation:

```python
naked_eye_composite = sum(
    factor_scores.get(factor, 50.0) * weight
    for factor, weight in NAKED_EYE_WEIGHTS.items()
) * _bortle_naked_eye_modifier(bortle)
```

Add `naked_eye_composite` to the returned `entry` dict alongside `composite`:

```python
entry = {
    "site":             site["name"],
    "date":             night_date.isoformat(),
    "composite":        round(composite, 1),
    "naked_eye":        round(naked_eye_composite, 1),   # ← add this
    "factors":          {k: round(v, 1) for k, v in factor_scores.items()},
    "stats": { ... },  # unchanged
}
```

Also add `"bortle_class"` to the stats dict so it's available to the UI:

```python
"stats": {
    ...existing keys...,
    "bortle_class": bortle,
}
```

No changes needed to `score_all` — it passes through whatever `score_forecast` returns.

---

## 2. `Planner.py` — display and sort

### 2a. Update sort radio options

Find the `st.radio` for `sort_by`. Replace the current options with:

```python
sort_by = st.radio(
    "Sort by",
    ["🔭 Telescope Score", "👁 Naked Eye Score", "Date", "Location"],
    horizontal=True,
    key="results_sort",
)
```

### 2b. Update sort logic

Replace the current sort conditionals:

```python
if sort_by == "Date":
    ranked = sorted(display, key=lambda n: (n["date"], -n["composite"]))
elif sort_by == "Location":
    ranked = sorted(display, key=lambda n: (n["site"], n["date"]))
elif sort_by == "👁 Naked Eye Score":
    ranked = sorted(display, key=lambda n: -n["naked_eye"])
else:  # 🔭 Telescope Score (default)
    ranked = sorted(display, key=lambda n: -n["composite"])
```

### 2c. Update the card header label

Find the line that builds `label` for `st.expander`. Replace the single score with both scores:

```python
tel_color = _score_color(night["composite"])
eye_color = _score_color(night["naked_eye"])
label = (
    f"🔭 :{tel_color}[**{night['composite']:.0f}**]"
    f"  👁 :{eye_color}[**{night['naked_eye']:.0f}**]"
    f" &nbsp; {date_str} &nbsp;·&nbsp; {night['site']}{dist_str}"
)
```

### 2d. Add Bortle to the expanded card metrics

Inside the expanded card where `_colored_metric` calls are made, add a Bortle display after the existing 8 metrics. Use a 9th column or place it in a new single-column row below:

```python
bortle = stats.get("bortle_class")
bortle_display = f"Class {bortle}" if bortle is not None else "—"
# Bortle 1–2 = green, 3–4 = yellow, 5+ = red (lower is better)
bortle_norm = _norm(bortle, 1, 9, higher_is_better=False) if bortle is not None else None
_colored_metric(c9, "Bortle", bortle_display, bortle_norm)
```

Add `c9 = cols[8]` to the column unpacking line (change `st.columns(8)` to `st.columns(9)`), or place Bortle in a new `st.columns(1)` row below — whichever fits the layout better visually.

### 2e. Update the heatmap (optional but recommended)

The heatmap currently pivots on `n["composite"]`. Consider adding a second heatmap tab or a radio to switch between telescope and naked eye heatmap views:

```python
heatmap_score = st.radio("Heatmap score", ["🔭 Telescope", "👁 Naked Eye"], horizontal=True, key="heatmap_score")
score_key = "composite" if heatmap_score == "🔭 Telescope" else "naked_eye"

pivot = (
    pd.DataFrame([{"site": n["site"], "date": n["date"], "score": n[score_key]} for n in filtered])
    .pivot_table(index="site", columns="date", values="score", aggfunc="first")
)
```

---

## Constraints

- Do not change any existing `factor_scores` keys or the telescope `composite` calculation — existing behavior must be identical
- Do not change `_load_weights()` or the `scoring_weights` DB table — telescope weights continue to come from the DB; naked eye weights are hardcoded constants (they are opinionated defaults, not user-configurable)
- Do not change the disqualifier logic — disqualification applies to both scores equally
- `naked_eye` should be `None`-safe in the UI: if for any reason it is missing from a night dict, fall back to displaying `—` rather than crashing
- The threshold filter (`min_score_threshold`) should continue to apply to `composite` (telescope) only — do not filter on naked eye score
