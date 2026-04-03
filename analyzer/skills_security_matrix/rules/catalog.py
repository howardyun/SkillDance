from __future__ import annotations


CONFIDENCE_PRIORITIES = {"high": 3, "medium": 2, "low": 1, "unknown": 0}


def highest_confidence(values: list[str]) -> str:
    return max(values, key=lambda value: CONFIDENCE_PRIORITIES.get(value, 0), default="unknown")


def bucket_confidence(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.45:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"
