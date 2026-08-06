from __future__ import annotations

import math
from dataclasses import dataclass, field

from .indicators import atr, bollinger, macd, rsi, sma
from .models import Bar, Signal


@dataclass
class SignalSettings:
    recent_days: int = 5
    ma_pairs: list[tuple[int, int]] = field(default_factory=lambda: [(5, 20), (20, 60)])
    breakout_windows: list[int] = field(default_factory=lambda: [20, 60])
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    boll_period: int = 20
    volume_period: int = 20
    volume_multiple: float = 2.0
    atr_period: int = 14


def scan_symbol(symbol: str, bars: list[Bar], settings: SignalSettings,
                timeframe: str = "1d") -> tuple[list[Signal], list[str]]:
    period_name = "周" if timeframe == "1w" else "日"
    minimum = max([slow for _, slow in settings.ma_pairs] + settings.breakout_windows + [settings.boll_period, 35])
    if len(bars) < minimum + 1:
        raise ValueError(f"{symbol} 至少需要 {minimum + 1} 根{period_name}线，当前只有 {len(bars)} 根")

    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    events: list[Signal] = []

    for fast, slow in settings.ma_pairs:
        fast_ma, slow_ma = sma(closes, fast), sma(closes, slow)
        for index in range(1, len(bars)):
            if _crossed_up(fast_ma, slow_ma, index):
                events.append(_event(symbol, bars[index], f"MA{fast}/MA{slow}金叉", "bullish",
                                     f"MA{fast} 上穿 MA{slow}", fast_ma[index] - slow_ma[index], timeframe))
            elif _crossed_down(fast_ma, slow_ma, index):
                events.append(_event(symbol, bars[index], f"MA{fast}/MA{slow}死叉", "bearish",
                                     f"MA{fast} 下穿 MA{slow}", fast_ma[index] - slow_ma[index], timeframe))

    dif, dea, histogram = macd(closes)
    for index in range(1, len(bars)):
        if _crossed_up(dif, dea, index):
            events.append(_event(symbol, bars[index], "MACD金叉", "bullish", "DIF 上穿 DEA", histogram[index], timeframe))
        elif _crossed_down(dif, dea, index):
            events.append(_event(symbol, bars[index], "MACD死叉", "bearish", "DIF 下穿 DEA", histogram[index], timeframe))

    rsi_values = rsi(closes, settings.rsi_period)
    for index in range(1, len(bars)):
        if rsi_values[index - 1] <= settings.rsi_oversold < rsi_values[index]:
            events.append(_event(symbol, bars[index], "RSI离开超卖区", "bullish",
                                 f"RSI({settings.rsi_period}) 上穿 {settings.rsi_oversold:g}", rsi_values[index], timeframe))
        elif rsi_values[index - 1] >= settings.rsi_overbought > rsi_values[index]:
            events.append(_event(symbol, bars[index], "RSI离开超买区", "bearish",
                                 f"RSI({settings.rsi_period}) 下穿 {settings.rsi_overbought:g}", rsi_values[index], timeframe))

    middle, upper, lower = bollinger(closes, settings.boll_period)
    for index in range(1, len(bars)):
        if _price_crossed_up(closes, upper, index):
            events.append(_event(symbol, bars[index], "BOLL上轨突破", "bullish", "收盘价上穿布林上轨", closes[index], timeframe))
        if _price_crossed_down(closes, lower, index):
            events.append(_event(symbol, bars[index], "BOLL下轨跌破", "bearish", "收盘价下穿布林下轨", closes[index], timeframe))
        if _price_crossed_up(closes, middle, index):
            events.append(_event(symbol, bars[index], "BOLL中轨上穿", "bullish", "收盘价上穿布林中轨", closes[index], timeframe))
        elif _price_crossed_down(closes, middle, index):
            events.append(_event(symbol, bars[index], "BOLL中轨下穿", "bearish", "收盘价下穿布林中轨", closes[index], timeframe))

    for window in settings.breakout_windows:
        for index in range(window + 1, len(bars)):
            previous_high = max(highs[index - window:index])
            previous_low = min(lows[index - window:index])
            if closes[index] > previous_high and closes[index - 1] <= max(highs[index - window - 1:index - 1]):
                events.append(_event(symbol, bars[index], f"{window}{period_name}新高突破", "bullish",
                                     f"收盘价突破此前 {window} {period_name}最高价 {previous_high:.2f}", closes[index], timeframe))
            if closes[index] < previous_low and closes[index - 1] >= min(lows[index - window - 1:index - 1]):
                events.append(_event(symbol, bars[index], f"{window}{period_name}新低跌破", "bearish",
                                     f"收盘价跌破此前 {window} {period_name}最低价 {previous_low:.2f}", closes[index], timeframe))

    volume_ma = sma(volumes, settings.volume_period)
    for index in range(settings.volume_period, len(bars)):
        if volume_ma[index - 1] > 0 and volumes[index] >= volume_ma[index - 1] * settings.volume_multiple:
            direction = "bullish" if closes[index] >= bars[index].open else "bearish"
            events.append(_event(symbol, bars[index], "成交量异常放大", direction,
                                 f"成交量达到前 {settings.volume_period} {period_name}均量的 {volumes[index] / volume_ma[index - 1]:.2f} 倍",
                                 volumes[index] / volume_ma[index - 1], timeframe))

    atr_values = atr(highs, lows, closes, settings.atr_period)
    states = _states(closes, bars, settings, dif, dea, histogram, rsi_values, middle, upper, lower, atr_values)
    return sorted(events, key=lambda item: (item.date, item.name)), states


def _states(closes: list[float], bars: list[Bar], settings: SignalSettings, dif: list[float], dea: list[float],
            histogram: list[float], rsi_values: list[float], middle: list[float], upper: list[float],
            lower: list[float], atr_values: list[float]) -> list[str]:
    states: list[str] = []
    ma5, ma20 = sma(closes, 5)[-1], sma(closes, 20)[-1]
    states.append(f"短期均线：MA5 {'高于' if ma5 > ma20 else '低于'} MA20（{ma5:.2f} / {ma20:.2f}）")
    states.append(f"MACD：DIF {'高于' if dif[-1] > dea[-1] else '低于'} DEA，柱值 {histogram[-1]:.3f}")
    states.append(f"RSI({settings.rsi_period})：{rsi_values[-1]:.2f}")
    boll_position = "上轨上方" if closes[-1] > upper[-1] else "下轨下方" if closes[-1] < lower[-1] else \
        "中轨上方" if closes[-1] >= middle[-1] else "中轨下方"
    states.append(f"BOLL：价格位于{boll_position}（中轨 {middle[-1]:.2f}）")
    if not math.isnan(atr_values[-1]):
        states.append(f"ATR({settings.atr_period})：{atr_values[-1]:.2f}，占收盘价 {atr_values[-1] / closes[-1] * 100:.2f}%")
    change = (closes[-1] / closes[-2] - 1) * 100
    states.insert(0, f"最新收盘：{bars[-1].date.isoformat()}，{closes[-1]:.2f}（{change:+.2f}%）")
    return states


def _crossed_up(first: list[float], second: list[float], index: int) -> bool:
    return _valid(first[index - 1], second[index - 1], first[index], second[index]) and \
        first[index - 1] <= second[index - 1] and first[index] > second[index]


def _crossed_down(first: list[float], second: list[float], index: int) -> bool:
    return _valid(first[index - 1], second[index - 1], first[index], second[index]) and \
        first[index - 1] >= second[index - 1] and first[index] < second[index]


def _price_crossed_up(prices: list[float], line: list[float], index: int) -> bool:
    return _valid(line[index - 1], line[index]) and prices[index - 1] <= line[index - 1] and prices[index] > line[index]


def _price_crossed_down(prices: list[float], line: list[float], index: int) -> bool:
    return _valid(line[index - 1], line[index]) and prices[index - 1] >= line[index - 1] and prices[index] < line[index]


def _valid(*values: float) -> bool:
    return all(not math.isnan(value) for value in values)


def _event(symbol: str, bar: Bar, name: str, direction: str, detail: str, value: float | None,
           timeframe: str) -> Signal:
    return Signal(symbol, bar.date, name, direction, detail, value, timeframe)
