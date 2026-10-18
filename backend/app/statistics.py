"""Small explainable statistics without an external model or heavy runtime."""

import math
from statistics import mean, median, pstdev


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def baseline(values: list[float]) -> dict:
    if not values:
        return {"trusted": False, "samples": 0}
    center = median(values)
    mad = median([abs(value - center) for value in values])
    ewma = values[0]
    for value in values[1:]:
        ewma = 0.3 * value + 0.7 * ewma
    deviation = pstdev(values)
    return {
        "samples": len(values),
        "trusted": len(values) >= 12,
        "mean": mean(values),
        "median": center,
        "mad": mad,
        "std": deviation,
        "p95": percentile(values, 0.95),
        "ewma": ewma,
        "threshold": max(5, center + 6 * max(mad, 1), mean(values) + 3 * deviation),
    }


def anomaly(value: float, stats: dict) -> dict:
    expected = stats.get("median", 0)
    score = (value - expected) / max(stats.get("mad", 1) * 1.4826, 1)
    zscore = (value - stats.get("mean", 0)) / max(stats.get("std", 1), 1)
    triggered = stats.get("trusted", False) and value > stats.get("threshold", math.inf)
    return {
        "triggered": bool(triggered),
        "robust_z_score": round(score, 2),
        "z_score": round(zscore, 2),
        "observed": value,
        "expected": expected,
        "threshold": stats.get("threshold"),
        "confidence": min(0.98, 0.6 + max(0, score) / 100) if triggered else 0,
    }
