from __future__ import annotations

from .models import Bar


def aggregate_weekly(bars: list[Bar]) -> list[Bar]:
    """Aggregate daily bars into Monday-based calendar weeks."""
    weeks: list[list[Bar]] = []
    for bar in sorted(bars, key=lambda item: item.date):
        key = bar.date.isocalendar()[:2]
        if not weeks or weeks[-1][0].date.isocalendar()[:2] != key:
            weeks.append([bar])
        else:
            weeks[-1].append(bar)
    return [
        Bar(week[-1].date, week[0].open, max(item.high for item in week),
            min(item.low for item in week), week[-1].close, sum(item.volume for item in week))
        for week in weeks
    ]


def confirmed_weekly_bars(daily_bars: list[Bar]) -> list[Bar]:
    """Return weekly bars, excluding a Monday-Thursday partial final week."""
    weekly = aggregate_weekly(daily_bars)
    if daily_bars and daily_bars[-1].date.weekday() < 4:
        return weekly[:-1]
    return weekly
