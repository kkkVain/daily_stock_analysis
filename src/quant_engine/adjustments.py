from __future__ import annotations

from datetime import date

from .config import SplitAdjustment
from .models import Bar


def apply_split_adjustments(bars: list[Bar], adjustments: list[SplitAdjustment]) -> tuple[list[Bar], list[str]]:
    """Put pre-split OHLCV on the latest per-share basis.

    For a 1:3 split, pre-effective-date prices are divided by 3 and volume is
    multiplied by 3. Applying rules in chronological order also handles more
    than one split without using future prices to infer the ratio.
    """
    result = list(bars)
    notes: list[str] = []
    for adjustment in sorted(adjustments, key=lambda item: item.effective_date):
        effective = date.fromisoformat(adjustment.effective_date)
        ratio = float(adjustment.ratio)
        if ratio <= 0:
            raise ValueError(f"拆分比例必须为正数：{ratio}")
        result = [
            Bar(bar.date, bar.open / ratio, bar.high / ratio, bar.low / ratio,
                bar.close / ratio, bar.volume * ratio) if bar.date < effective else bar
            for bar in result
        ]
        notes.append(f"{effective} {adjustment.description} 1:{ratio:g}；此前价格÷{ratio:g}、成交量×{ratio:g}")
    return result, notes
