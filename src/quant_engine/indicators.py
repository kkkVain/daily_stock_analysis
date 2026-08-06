from __future__ import annotations

import math
from collections.abc import Sequence


NAN = float("nan")


def sma(values: Sequence[float], period: int) -> list[float]:
    result = [NAN] * len(values)
    if period <= 0:
        raise ValueError("period must be positive")
    rolling = 0.0
    for index, value in enumerate(values):
        rolling += value
        if index >= period:
            rolling -= values[index - period]
        if index >= period - 1:
            result[index] = rolling / period
    return result


def ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def rolling_std(values: Sequence[float], period: int) -> list[float]:
    result = [NAN] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        mean = sum(window) / period
        result[index] = math.sqrt(sum((value - mean) ** 2 for value in window) / period)
    return result


def rsi(values: Sequence[float], period: int = 14) -> list[float]:
    result = [NAN] * len(values)
    if len(values) <= period:
        return result
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = _rsi_value(avg_gain, avg_loss)
    for index in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[index - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index - 1]) / period
        result[index] = _rsi_value(avg_gain, avg_loss)
    return result


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1 + avg_gain / avg_loss)


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float], list[float], list[float]]:
    fast_line, slow_line = ema(values, fast), ema(values, slow)
    dif = [fast_value - slow_value for fast_value, slow_value in zip(fast_line, slow_line)]
    dea = ema(dif, signal)
    histogram = [(dif_value - dea_value) * 2 for dif_value, dea_value in zip(dif, dea)]
    return dif, dea, histogram


def bollinger(values: Sequence[float], period: int = 20, deviations: float = 2.0) -> tuple[list[float], list[float], list[float]]:
    middle = sma(values, period)
    std = rolling_std(values, period)
    upper = [m + deviations * s if not math.isnan(m) else NAN for m, s in zip(middle, std)]
    lower = [m - deviations * s if not math.isnan(m) else NAN for m, s in zip(middle, std)]
    return middle, upper, lower


def atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int = 14) -> list[float]:
    if not close:
        return []
    true_ranges = [high[0] - low[0]]
    for index in range(1, len(close)):
        true_ranges.append(max(high[index] - low[index], abs(high[index] - close[index - 1]),
                               abs(low[index] - close[index - 1])))
    return wilder(true_ranges, period)


def wilder(values: Sequence[float], period: int) -> list[float]:
    """Wilder moving average (RMA), seeded with the first period's SMA."""
    result = [NAN] * len(values)
    if len(values) < period:
        return result
    result[period - 1] = sum(values[:period]) / period
    for index in range(period, len(values)):
        result[index] = (result[index - 1] * (period - 1) + values[index]) / period
    return result


def dmi_adx(high: Sequence[float], low: Sequence[float], close: Sequence[float],
            period: int = 14) -> tuple[list[float], list[float], list[float]]:
    count = len(close)
    tr, plus_dm, minus_dm = [0.0] * count, [0.0] * count, [0.0] * count
    if not close:
        return [], [], []
    tr[0] = high[0] - low[0]
    for index in range(1, count):
        up, down = high[index] - high[index - 1], low[index - 1] - low[index]
        plus_dm[index] = up if up > down and up > 0 else 0.0
        minus_dm[index] = down if down > up and down > 0 else 0.0
        tr[index] = max(high[index] - low[index], abs(high[index] - close[index - 1]),
                        abs(low[index] - close[index - 1]))
    atr_line, plus_rma, minus_rma = wilder(tr, period), wilder(plus_dm, period), wilder(minus_dm, period)
    plus_di, minus_di, dx = [NAN] * count, [NAN] * count, [NAN] * count
    for index in range(period - 1, count):
        if atr_line[index] > 0:
            plus_di[index] = 100 * plus_rma[index] / atr_line[index]
            minus_di[index] = 100 * minus_rma[index] / atr_line[index]
            total = plus_di[index] + minus_di[index]
            dx[index] = 100 * abs(plus_di[index] - minus_di[index]) / total if total else 0.0
    adx = [NAN] * count
    first = period * 2 - 2
    if count > first:
        adx[first] = sum(dx[period - 1:first + 1]) / period
        for index in range(first + 1, count):
            adx[index] = (adx[index - 1] * (period - 1) + dx[index]) / period
    return plus_di, minus_di, adx


def stochastic_kdj(high: Sequence[float], low: Sequence[float], close: Sequence[float],
                   period: int = 9, smooth_k: int = 3, smooth_d: int = 3) -> tuple[list[float], list[float], list[float]]:
    count = len(close)
    k, d, j = [NAN] * count, [NAN] * count, [NAN] * count
    previous_k = previous_d = 50.0
    for index in range(period - 1, count):
        highest = max(high[index - period + 1:index + 1])
        lowest = min(low[index - period + 1:index + 1])
        rsv = 50.0 if highest == lowest else 100 * (close[index] - lowest) / (highest - lowest)
        previous_k = (smooth_k - 1) / smooth_k * previous_k + rsv / smooth_k
        previous_d = (smooth_d - 1) / smooth_d * previous_d + previous_k / smooth_d
        k[index], d[index], j[index] = previous_k, previous_d, 3 * previous_k - 2 * previous_d
    return k, d, j


def cci(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int = 20) -> list[float]:
    typical = [(h + l + c) / 3 for h, l, c in zip(high, low, close)]
    result = [NAN] * len(close)
    for index in range(period - 1, len(close)):
        window = typical[index - period + 1:index + 1]
        mean = sum(window) / period
        deviation = sum(abs(value - mean) for value in window) / period
        result[index] = (typical[index] - mean) / (.015 * deviation) if deviation else 0.0
    return result


def roc(values: Sequence[float], period: int = 12) -> list[float]:
    result = [NAN] * len(values)
    for index in range(period, len(values)):
        result[index] = (values[index] / values[index - period] - 1) * 100 if values[index - period] else NAN
    return result


def obv(close: Sequence[float], volume: Sequence[float]) -> list[float]:
    if not close:
        return []
    result = [0.0]
    for index in range(1, len(close)):
        change = volume[index] if close[index] > close[index - 1] else -volume[index] if close[index] < close[index - 1] else 0
        result.append(result[-1] + change)
    return result


def supertrend(high: Sequence[float], low: Sequence[float], close: Sequence[float],
               period: int = 10, multiplier: float = 3.0) -> tuple[list[float], list[int]]:
    atr_line = atr(high, low, close, period)
    line, direction = [NAN] * len(close), [0] * len(close)
    upper, lower = [NAN] * len(close), [NAN] * len(close)
    start = period - 1
    if len(close) <= start:
        return line, direction
    middle = (high[start] + low[start]) / 2
    upper[start], lower[start] = middle + multiplier * atr_line[start], middle - multiplier * atr_line[start]
    direction[start] = 1 if close[start] >= middle else -1
    line[start] = lower[start] if direction[start] > 0 else upper[start]
    for index in range(start + 1, len(close)):
        middle = (high[index] + low[index]) / 2
        basic_upper, basic_lower = middle + multiplier * atr_line[index], middle - multiplier * atr_line[index]
        upper[index] = basic_upper if basic_upper < upper[index - 1] or close[index - 1] > upper[index - 1] else upper[index - 1]
        lower[index] = basic_lower if basic_lower > lower[index - 1] or close[index - 1] < lower[index - 1] else lower[index - 1]
        if direction[index - 1] < 0 and close[index] > upper[index]:
            direction[index] = 1
        elif direction[index - 1] > 0 and close[index] < lower[index]:
            direction[index] = -1
        else:
            direction[index] = direction[index - 1]
        line[index] = lower[index] if direction[index] > 0 else upper[index]
    return line, direction
