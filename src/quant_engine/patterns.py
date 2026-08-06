from __future__ import annotations

import math

from .indicators import atr
from .models import Bar, Signal


def scan_graphical_patterns(symbol: str, bars: list[Bar], timeframe: str = "1d",
                            level_window: int = 40, channel_window: int = 40) -> tuple[list[Signal], list[str]]:
    """Detect explicit price-action patterns without using future bars."""
    if len(bars) < max(level_window, channel_window) + 2:
        return [], []
    events: list[Signal] = []
    closes = [bar.close for bar in bars]
    atr_values = atr([bar.high for bar in bars], [bar.low for bar in bars], closes, 14)

    for index in range(1, len(bars)):
        bar, previous = bars[index], bars[index - 1]
        threshold = 0.15 * atr_values[index - 1] if not math.isnan(atr_values[index - 1]) else 0.0
        if bar.low > previous.high and bar.low - previous.high >= threshold:
            events.append(_event(symbol, bar, "向上跳空缺口", "bullish",
                                 f"最低价 {bar.low:.2f} 高于前一根最高价 {previous.high:.2f}", timeframe))
        elif bar.high < previous.low and previous.low - bar.high >= threshold:
            events.append(_event(symbol, bar, "向下跳空缺口", "bearish",
                                 f"最高价 {bar.high:.2f} 低于前一根最低价 {previous.low:.2f}", timeframe))

        body = abs(bar.close - bar.open)
        span = max(bar.high - bar.low, 1e-12)
        upper_shadow = bar.high - max(bar.open, bar.close)
        lower_shadow = min(bar.open, bar.close) - bar.low
        if body / span <= 0.1:
            events.append(_event(symbol, bar, "十字星", "neutral", "实体不超过当期振幅的 10%", timeframe))
        if lower_shadow >= max(body * 2, span * 0.4) and upper_shadow <= span * 0.2:
            events.append(_event(symbol, bar, "锤头线", "bullish", "下影线至少为实体两倍且上影较短", timeframe))
        if upper_shadow >= max(body * 2, span * 0.4) and lower_shadow <= span * 0.2:
            events.append(_event(symbol, bar, "射击之星", "bearish", "上影线至少为实体两倍且下影较短", timeframe))
        if previous.close < previous.open and bar.close > bar.open and \
                bar.open <= previous.close and bar.close >= previous.open:
            events.append(_event(symbol, bar, "看涨吞没", "bullish", "阳线实体包住前一根阴线实体", timeframe))
        if previous.close > previous.open and bar.close < bar.open and \
                bar.open >= previous.close and bar.close <= previous.open:
            events.append(_event(symbol, bar, "看跌吞没", "bearish", "阴线实体包住前一根阳线实体", timeframe))

    for index in range(level_window + 1, len(bars)):
        resistance = max(item.high for item in bars[index - level_window:index])
        support = min(item.low for item in bars[index - level_window:index])
        old_resistance = max(item.high for item in bars[index - level_window - 1:index - 1])
        old_support = min(item.low for item in bars[index - level_window - 1:index - 1])
        if bars[index].close > resistance and bars[index - 1].close <= old_resistance:
            events.append(_event(symbol, bars[index], "阻力位突破", "bullish",
                                 f"收盘价突破前 {level_window} 期阻力 {resistance:.2f}", timeframe))
        if bars[index].close < support and bars[index - 1].close >= old_support:
            events.append(_event(symbol, bars[index], "支撑位跌破", "bearish",
                                 f"收盘价跌破前 {level_window} 期支撑 {support:.2f}", timeframe))

    for index in range(channel_window + 1, len(bars)):
        position, upper, lower = _channel_position(closes[index - channel_window:index], closes[index])
        old_position, _, _ = _channel_position(closes[index - channel_window - 1:index - 1], closes[index - 1])
        if position > 1 and old_position <= 1:
            events.append(_event(symbol, bars[index], "上破趋势通道", "bullish",
                                 f"收盘价上破 {channel_window} 期回归通道上沿 {upper:.2f}", timeframe))
        elif position < -1 and old_position >= -1:
            events.append(_event(symbol, bars[index], "下破趋势通道", "bearish",
                                 f"收盘价下破 {channel_window} 期回归通道下沿 {lower:.2f}", timeframe))

    resistance = max(item.high for item in bars[-level_window:])
    support = min(item.low for item in bars[-level_window:])
    position, upper, lower = _channel_position(closes[-channel_window:], closes[-1])
    channel_state = "上沿外" if position > 1 else "下沿外" if position < -1 else "通道内"
    states = [f"近 {level_window} 期支撑/阻力：{support:.2f} / {resistance:.2f}",
              f"{channel_window} 期趋势通道：价格位于{channel_state}（{lower:.2f}–{upper:.2f}）"]
    return sorted(events, key=lambda item: (item.date, item.name)), states


def _channel_position(window: list[float], current: float) -> tuple[int, float, float]:
    count = len(window)
    x_mean = (count - 1) / 2
    y_mean = sum(window) / count
    denominator = sum((index - x_mean) ** 2 for index in range(count))
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(window)) / denominator
    intercept = y_mean - slope * x_mean
    residuals = [value - (intercept + slope * index) for index, value in enumerate(window)]
    deviation = math.sqrt(sum(value * value for value in residuals) / count)
    center = intercept + slope * count
    width = max(2 * deviation, abs(center) * 0.002)
    upper, lower = center + width, center - width
    return (2 if current > upper else -2 if current < lower else 0), upper, lower


def _event(symbol: str, bar: Bar, name: str, direction: str, detail: str, timeframe: str) -> Signal:
    return Signal(symbol, bar.date, name, direction, detail, bar.close, timeframe)
