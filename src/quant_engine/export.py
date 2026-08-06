from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import ScanResult


def result_to_dict(result: ScanResult, recent_days: int) -> dict[str, Any]:
    """Build the stable, machine-readable result consumed by other applications."""
    events = [event.to_dict() for event in result.events]
    readings = [asdict(item) for item in (result.indicator_readings or [])]
    weekly_readings = [asdict(item) for item in (result.weekly_indicator_readings or [])]
    quality = asdict(result.data_quality) if result.data_quality else None
    if quality and isinstance(quality.get("issues"), tuple):
        quality["issues"] = list(quality["issues"])

    forecast = None
    if result.forecast:
        forecast = asdict(result.forecast)
        forecast["points"] = [
            {**asdict(point), "date": point.date.isoformat()}
            for point in result.forecast.points
        ]

    return {
        "schema_version": "1.0",
        "symbol": result.symbol,
        "display_name": result.display_name or result.symbol,
        "as_of": result.as_of.isoformat(),
        "last_close": result.last_close,
        "source": result.source_status or result.source,
        "data_quality": quality,
        "adjustments": list(result.adjustment_notes or []),
        "technical": {
            "states": list(result.states),
            "weekly_states": list(result.weekly_states),
            "indicator_readings": readings,
            "weekly_indicator_readings": weekly_readings,
            "events": events,
            "new_event_ids": sorted(result.new_event_ids),
            "recent_days": recent_days,
        },
        "kronos": forecast,
        "validation": None,
        # Kept in the runner contract so the validator uses the exact same
        # adjusted price series.  Consumers may discard it before persistence.
        "history": [
            {**asdict(bar), "date": bar.date.isoformat()} for bar in result.bars
        ],
    }


def results_to_dict(results: list[ScanResult], recent_days: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "results": [result_to_dict(result, recent_days) for result in results],
    }
