"""Analytics arithmetic — pure, deterministic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import analytics


def test_growth():
    assert analytics.growth([100, 120, 150]) == 50.0
    assert analytics.growth([]) == 0.0
    assert analytics.growth([42]) == 0.0


def test_average_views():
    assert analytics.average_views([100, 200, 300]) == 200.0
    assert analytics.average_views([]) == 0.0


def test_detect_anomaly_flags_spike():
    baseline = [100, 110, 90, 105, 95]  # ~100 avg, small spread
    result = analytics.detect_anomaly(500, baseline)
    assert result.is_anomaly is True
    assert result.z_score >= 2.0


def test_detect_anomaly_normal_value():
    baseline = [100, 110, 90, 105, 95]
    result = analytics.detect_anomaly(102, baseline)
    assert result.is_anomaly is False


def test_detect_anomaly_insufficient_baseline():
    result = analytics.detect_anomaly(1000, [100])
    assert result.is_anomaly is False  # not enough data to judge


def test_days_since():
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    earlier = now - timedelta(days=3)
    assert analytics.days_since(earlier, now) == 3.0
    assert analytics.days_since(None, now) is None
