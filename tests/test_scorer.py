"""
Scorer unit tests.

Covers:
  - Per-factor scorer functions (pure, no deps)
  - _bortle_naked_eye_modifier (QA 2.6, 2.7, 2.9)
  - NAKED_EYE_WEIGHTS sanity (weights sum to 1.0)
  - _avg and _night_key helpers
  - score_forecast output shape and Bortle logic (QA 2.6, 2.7, 2.9, 7.3)
    with _load_weights mocked to avoid DB dependency
"""

import math
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# Make the project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scorer import (
    _score_cloud_cover,
    _score_high_cloud,
    _score_lifted_index,
    _score_humidity,
    _score_moon,
    _bortle_naked_eye_modifier,
    _avg,
    _night_key,
    NAKED_EYE_WEIGHTS,
    score_forecast,
)


# ── Per-factor scorers ─────────────────────────────────────────────────────────

class TestScoreCloudCover:
    def test_clear_sky(self):
        assert _score_cloud_cover(0) == 100.0

    def test_fully_overcast(self):
        assert _score_cloud_cover(100) == 0.0

    def test_partial(self):
        assert _score_cloud_cover(40) == 60.0

    def test_no_negative(self):
        assert _score_cloud_cover(110) == 0.0


class TestScoreHighCloud:
    def test_no_high_cloud(self):
        assert _score_high_cloud(0) == 100.0

    def test_full_high_cloud(self):
        assert _score_high_cloud(100) == 0.0

    def test_no_negative(self):
        assert _score_high_cloud(150) == 0.0


class TestScoreLiftedIndex:
    def test_very_stable(self):
        # LI = +5 → best stability
        score = _score_lifted_index(5)
        assert score == 100.0

    def test_very_unstable(self):
        # LI = -10 → worst stability
        score = _score_lifted_index(-10)
        assert score == 0.0

    def test_neutral(self):
        # LI = -2.5 → midpoint of [-10, +5]
        score = _score_lifted_index(-2.5)
        assert abs(score - 50.0) < 0.1

    def test_clamps_above(self):
        assert _score_lifted_index(99) == 100.0

    def test_clamps_below(self):
        assert _score_lifted_index(-99) == 0.0


class TestScoreHumidity:
    def test_low_humidity(self):
        # Below 60 RH → full score
        assert _score_humidity(30) == 100.0

    def test_at_threshold(self):
        assert _score_humidity(60) == 100.0

    def test_high_humidity(self):
        assert _score_humidity(100) == 0.0

    def test_no_negative(self):
        assert _score_humidity(200) == 0.0

    def test_midpoint(self):
        # 80 RH → halfway between 60 and 100 penalty range
        assert abs(_score_humidity(80) - 50.0) < 0.1


class TestScoreMoon:
    def test_returns_in_range(self):
        # Just verify output is 0–100 for a variety of dates/locations
        score = _score_moon(datetime(2026, 1, 15).date(), 30.0, -100.0, "America/Chicago")
        assert 0.0 <= score <= 100.0

    def test_favorable_night_scores_high(self):
        # 2026-01-03: moon sets well before dark ends → score = 100
        score = _score_moon(datetime(2026, 1, 3).date(), 30.0, -100.0, "America/Chicago")
        assert score >= 70.0

    def test_unfavorable_night_scores_low(self):
        # 2026-01-02: bright moon present most of the night → score ≈ 7.5
        score = _score_moon(datetime(2026, 1, 2).date(), 30.0, -100.0, "America/Chicago")
        assert score <= 15.0


# ── Bortle modifier (QA 2.6, 2.7, 2.9) ───────────────────────────────────────

class TestBortleNakedEyeModifier:
    def test_bortle_1_no_penalty(self):
        assert _bortle_naked_eye_modifier(1) == 1.0

    def test_bortle_2_no_penalty(self):
        assert _bortle_naked_eye_modifier(2) == 1.0

    def test_bortle_3_mild_penalty(self):
        assert _bortle_naked_eye_modifier(3) == 0.92

    def test_bortle_4_mild_penalty(self):
        assert _bortle_naked_eye_modifier(4) == 0.84

    def test_bortle_5_moderate_penalty(self):
        assert _bortle_naked_eye_modifier(5) == 0.75

    def test_bortle_6_moderate_penalty(self):
        assert _bortle_naked_eye_modifier(6) == 0.70

    def test_bortle_7_heavy_penalty(self):
        # QA 2.6: Bortle 7+ → modifier ≤ 0.65
        assert _bortle_naked_eye_modifier(7) <= 0.65

    def test_bortle_8_heavy_penalty(self):
        assert _bortle_naked_eye_modifier(8) <= 0.65

    def test_bortle_9_heavy_penalty(self):
        assert _bortle_naked_eye_modifier(9) <= 0.65

    def test_none_returns_one(self):
        # QA 2.9: unknown Bortle → no penalty
        assert _bortle_naked_eye_modifier(None) == 1.0

    def test_all_modifiers_in_range(self):
        for b in range(1, 10):
            m = _bortle_naked_eye_modifier(b)
            assert 0.0 <= m <= 1.0, f"Bortle {b} modifier {m} out of range"

    def test_monotonically_non_increasing(self):
        # Higher Bortle class should never improve the modifier
        modifiers = [_bortle_naked_eye_modifier(b) for b in range(1, 10)]
        for i in range(len(modifiers) - 1):
            assert modifiers[i] >= modifiers[i + 1], (
                f"Bortle {i+1} modifier {modifiers[i]} < Bortle {i+2} modifier {modifiers[i+1]}"
            )


# ── NAKED_EYE_WEIGHTS ─────────────────────────────────────────────────────────

class TestNakedEyeWeights:
    def test_weights_sum_to_one(self):
        total = sum(NAKED_EYE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    def test_seeing_excluded(self):
        assert "seeing_7timer" not in NAKED_EYE_WEIGHTS
        assert "transparency_7timer" not in NAKED_EYE_WEIGHTS

    def test_all_weights_positive(self):
        for factor, w in NAKED_EYE_WEIGHTS.items():
            assert w > 0, f"Weight for {factor} is not positive"


# ── Helpers ───────────────────────────────────────────────────────────────────

class TestAvg:
    def test_basic(self):
        assert _avg([10, 20, 30]) == 20.0

    def test_empty(self):
        assert _avg([]) is None

    def test_all_none(self):
        assert _avg([None, None]) is None

    def test_filters_none(self):
        assert _avg([10, None, 30]) == 20.0

    def test_filters_nan(self):
        assert _avg([10.0, float("nan"), 30.0]) == 20.0

    def test_single_value(self):
        assert _avg([42]) == 42.0


class TestNightKey:
    def test_evening_hour_is_same_date(self):
        # 9pm on July 1 → night of July 1
        from datetime import date
        result = _night_key("2026-07-01T21:00")
        assert result == date(2026, 7, 1)

    def test_midnight_belongs_to_previous_night(self):
        # 1am on July 2 → night of July 1
        from datetime import date
        result = _night_key("2026-07-02T01:00")
        assert result == date(2026, 7, 1)

    def test_noon_boundary(self):
        # Exactly noon on July 2 → night of July 2
        from datetime import date
        result = _night_key("2026-07-02T12:00")
        assert result == date(2026, 7, 2)

    def test_pre_noon_belongs_to_previous_night(self):
        # 11am on July 2 → night of July 1
        from datetime import date
        result = _night_key("2026-07-02T11:00")
        assert result == date(2026, 7, 1)


# ── score_forecast (mocked DB) ────────────────────────────────────────────────

def _make_forecast(bortle_class, cloud=20, hi_cloud=10, humidity=50, li=2.0, precip=5):
    """Build a minimal forecast dict for one nighttime period (8 hours)."""
    # 8 evening hours: 20:00–23:00 on day 1, 00:00–03:00 on day 2
    # All map to the same observing night via _night_key
    base = datetime(2026, 7, 1, 20, 0)
    times = [(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(8)]
    n = len(times)
    return {
        "site": {
            "name": "Test Site",
            "lat": 30.67,
            "lon": -104.02,
            "bortle_class": bortle_class,
        },
        "open_meteo": {
            "hourly": {
                "time":                     times,
                "is_day":                   [0] * n,
                "cloud_cover":              [cloud] * n,
                "cloud_cover_high":         [hi_cloud] * n,
                "lifted_index":             [li] * n,
                "relative_humidity_2m":     [humidity] * n,
                "precipitation_probability":[precip] * n,
                "visibility":               [20000] * n,  # 20 km
            }
        },
        "seven_timer": None,
        "errors": [],
    }

# Default telescope weights for mocking
_DEFAULT_WEIGHTS = {
    "cloud_cover":  0.40,
    "moon":         0.20,
    "high_cloud":   0.15,
    "humidity":     0.15,
    "lifted_index": 0.10,
}


class TestScoreForecast:
    def _run(self, forecast, disqualifiers=None):
        with patch("scorer._load_weights", return_value=_DEFAULT_WEIGHTS):
            return score_forecast(forecast, "America/Chicago", disqualifiers)

    def test_returns_list_of_nights(self):
        results = self._run(_make_forecast(bortle_class=3))
        assert isinstance(results, list)
        assert len(results) == 1

    def test_result_has_required_keys(self):
        night = self._run(_make_forecast(bortle_class=3))[0]
        for key in ("site", "date", "composite", "naked_eye", "factors", "stats"):
            assert key in night, f"Missing key: {key}"

    def test_bortle_class_in_stats(self):
        # QA 2.9 / 7.3
        night = self._run(_make_forecast(bortle_class=4))[0]
        assert night["stats"]["bortle_class"] == 4

    def test_bortle_none_in_stats(self):
        # QA 2.9: site without Bortle class
        night = self._run(_make_forecast(bortle_class=None))[0]
        assert night["stats"]["bortle_class"] is None

    def test_naked_eye_lower_for_high_bortle(self):
        # QA 2.6: Bortle 7+ → naked_eye < composite (assuming clear sky so composite is high)
        night = self._run(_make_forecast(bortle_class=7, cloud=5, humidity=30))[0]
        assert night["naked_eye"] < night["composite"], (
            f"Expected naked_eye ({night['naked_eye']}) < composite ({night['composite']}) for Bortle 7"
        )

    def test_naked_eye_not_penalised_for_low_bortle(self):
        # QA 2.7: Bortle 1–2 → modifier = 1.0 → naked_eye difference is weight-only
        night_b1 = self._run(_make_forecast(bortle_class=1, cloud=5, humidity=30))[0]
        night_b2 = self._run(_make_forecast(bortle_class=2, cloud=5, humidity=30))[0]
        assert night_b1["naked_eye"] == night_b2["naked_eye"]

    def test_naked_eye_none_bortle_equals_bortle_1(self):
        # QA 2.9 / 7.3: modifier(None) == modifier(1) == 1.0, so scores should match
        night_none = self._run(_make_forecast(bortle_class=None, cloud=10, humidity=40))[0]
        night_b1   = self._run(_make_forecast(bortle_class=1,    cloud=10, humidity=40))[0]
        assert night_none["naked_eye"] == night_b1["naked_eye"]

    def test_composite_unaffected_by_bortle(self):
        # Telescope score must not change based on Bortle class
        night_b1 = self._run(_make_forecast(bortle_class=1,  cloud=30))[0]
        night_b9 = self._run(_make_forecast(bortle_class=9,  cloud=30))[0]
        assert night_b1["composite"] == night_b9["composite"]

    def test_naked_eye_monotonically_decreases_with_bortle(self):
        # QA 7.3: higher Bortle → lower or equal naked_eye score
        scores = [
            self._run(_make_forecast(bortle_class=b, cloud=10, humidity=30))[0]["naked_eye"]
            for b in range(1, 10)
        ]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"naked_eye at Bortle {i+1} ({scores[i]}) < Bortle {i+2} ({scores[i+1]})"
            )

    def test_disqualifier_sets_flag(self):
        forecast = _make_forecast(bortle_class=2, cloud=90)
        results = self._run(forecast, disqualifiers={"max_cloud_cover": 50})
        assert len(results) == 1
        assert "disqualified" in results[0]
        assert "Cloud cover" in results[0]["disqualified"]

    def test_no_disqualifier_when_within_limits(self):
        forecast = _make_forecast(bortle_class=2, cloud=30)
        results = self._run(forecast, disqualifiers={"max_cloud_cover": 50})
        assert "disqualified" not in results[0]

    def test_scores_in_valid_range(self):
        night = self._run(_make_forecast(bortle_class=5, cloud=50, humidity=70))[0]
        assert 0 <= night["composite"] <= 100
        assert 0 <= night["naked_eye"] <= 100

    def test_empty_open_meteo_returns_empty(self):
        forecast = _make_forecast(bortle_class=2)
        forecast["open_meteo"] = None
        results = self._run(forecast)
        assert results == []
