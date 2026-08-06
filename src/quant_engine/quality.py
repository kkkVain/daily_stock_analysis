from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Bar


@dataclass(frozen=True)
class DataQuality:
    status: str
    analyzable: bool
    summary: str
    issues: tuple[str, ...] = ()


def assess_data_quality(bars: list[Bar], minimum_bars: int = 80, jump_limit: float = .25) -> DataQuality:
    issues: list[str] = []
    fatal: list[str] = []
    if len(bars) < minimum_bars:
        fatal.append(f"历史仅 {len(bars)} 根，少于最低要求 {minimum_bars} 根")
    if not bars:
        return DataQuality("禁止分析", False, "没有有效行情", ("行情为空",))
    seen: set[date] = set()
    for bar in bars:
        if bar.date in seen:
            fatal.append(f"存在重复日期 {bar.date}")
        seen.add(bar.date)
        if min(bar.open, bar.high, bar.low, bar.close) <= 0 or bar.low > bar.high:
            fatal.append(f"{bar.date} OHLC 非法")
    for previous, current in zip(bars, bars[1:]):
        close_change = current.close / previous.close - 1
        # Mainland ETFs/stocks normally cannot move 25% in one session. A larger
        # discontinuity is more likely a split/fund conversion or mixed adjustment.
        if abs(close_change) >= jump_limit:
            fatal.append(f"{current.date} 收盘跳变 {close_change:+.2%}（{previous.close:.3f}→{current.close:.3f}），疑似折算/复权断点")
    latest_age = (date.today() - bars[-1].date).days
    if latest_age > 7:
        issues.append(f"最新行情距今天 {latest_age} 天，可能已过期")
    all_issues = tuple(fatal + issues)
    if fatal:
        return DataQuality("禁止分析", False, "检测到会污染指标或模型的价格断点", all_issues)
    if issues:
        return DataQuality("警告", True, "行情可分析，但存在时效性警告", all_issues)
    return DataQuality("正常", True, f"{len(bars)} 根连续有效行情，未发现 ≥{jump_limit:.0%} 的异常跳变")
