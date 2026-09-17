"""Pure analytics helpers — no DB, no network, fully unit-tested.

Kept pure on purpose: these are the arithmetic the dashboard trusts, so they are
tested directly (tests/test_analytics.py) with plain numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


def growth(series: list[int | float]) -> float:
    """Absolute change between first and last point of a series."""
    clean = [v for v in series if v is not None]
    if len(clean) < 2:
        return 0.0
    return float(clean[-1] - clean[0])


def average_views(views: list[int]) -> float:
    return round(mean(views), 2) if views else 0.0


@dataclass
class Anomaly:
    value: float
    mean: float
    z_score: float
    is_anomaly: bool


def detect_anomaly(value: float, baseline: list[float], threshold: float = 2.0) -> Anomaly:
    """Flag a value that deviates from the channel baseline by > threshold sigma.

    Deterministic and cheap — this is the "sharp spike vs usual" signal and it
    needs no LLM. (The LLM is used for the qualitative digest/category instead.)
    """
    clean = [float(v) for v in baseline if v is not None]
    if len(clean) < 3:
        return Anomaly(value=value, mean=(clean[0] if clean else 0.0), z_score=0.0, is_anomaly=False)
    mu = mean(clean)
    sigma = pstdev(clean)
    if sigma == 0:
        z = 0.0
    else:
        z = (value - mu) / sigma
    return Anomaly(value=value, mean=round(mu, 2), z_score=round(z, 2), is_anomaly=z >= threshold)


def days_since(latest, now) -> float | None:
    """Whole+fractional days between two aware datetimes (used for source health
    and the 'not posted in N days' alert)."""
    if latest is None or now is None:
        return None
    return (now - latest).total_seconds() / 86400.0
