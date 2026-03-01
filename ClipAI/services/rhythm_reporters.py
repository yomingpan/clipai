from __future__ import annotations


def build_daily_summary(metrics: list[dict]) -> dict:
    count = len(metrics)
    avg_tempo = 0.0 if count == 0 else sum(float(m.get("tempo", 0.0)) for m in metrics) / count
    return {"count": count, "avg_tempo": avg_tempo}


def build_weekly_summary(days: list[dict]) -> dict:
    count = len(days)
    avg_tempo = 0.0 if count == 0 else sum(float(d.get("avg_tempo", 0.0)) for d in days) / count
    return {"days": count, "avg_tempo": avg_tempo}
