# Claude Code Prompt: Add `seven_timer_tier` to Scorer

## Context

This is a Python stargazing conditions app. The scorer (`scorer.py`) produces nightly forecast results for multiple sites. Each night entry currently has a `stats` dict containing `seeing_7timer` and `transparency_7timer` — raw averages from 7timer's ASTRO product (scale 1–8, where 1 is best). These are currently display-only and not part of any composite score.

## Task

Add a `seven_timer_tier` field to each night result dict in `scorer.py` (inside `score_forecast`).

## Requirements

1. Invert both seeing and transparency from the 1–8 scale to 0–100 (1 → 100, 8 → 0)
2. Blend them at **65% seeing / 35% transparency** into a single score
3. Bucket into tiers:
   - `"mediocre"` — blended score < 40
   - `"good"` — blended score 40–69
   - `"excellent"` — blended score ≥ 70
4. If either or both values are missing/None, tier should be `"no_data"` and score should be `None`
5. The output field should be a dict:
   ```python
   {
       "tier": str,           # "mediocre" | "good" | "excellent" | "no_data"
       "score": float | None, # blended 0–100 value, or None if no data
       "seeing": float | None,
       "transparency": float | None
   }
   ```
6. Do not touch composite scoring logic, weights, or any other fields — this is purely additive
7. Review the full repo before making changes to ensure the new field is handled anywhere `score_forecast` output is consumed (API responses, DB writes, display layers, etc.)
