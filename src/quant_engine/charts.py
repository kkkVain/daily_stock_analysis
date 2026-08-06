from __future__ import annotations

import html
import math

from .indicators import macd, rsi, sma
from .models import Bar, Signal


def render_technical_chart(bars: list[Bar], events: list[Signal], limit: int = 120) -> str:
    shown = bars[-limit:]
    if not shown:
        return ""
    width, height, left, right = 960, 640, 58, 18
    plot_width = width - left - right
    price_top, price_height = 25, 315
    volume_top, volume_height = 355, 75
    macd_top, macd_height = 450, 75
    rsi_top, rsi_height = 545, 70
    step = plot_width / len(shown)
    closes = [bar.close for bar in shown]
    all_closes = [bar.close for bar in bars]
    ma_lines = {period: sma(all_closes, period)[-len(shown):] for period in (5, 20, 60)}
    price_values = [value for bar in shown for value in (bar.high, bar.low)]
    price_values += [value for line in ma_lines.values() for value in line if not math.isnan(value)]
    low, high = min(price_values), max(price_values)
    padding = max((high - low) * 0.05, abs(high) * 0.002)
    low, high = low - padding, high + padding
    x_at = lambda index: left + (index + 0.5) * step
    y_at = lambda value: price_top + (high - value) / (high - low) * price_height
    parts = [f"<svg class='chart' viewBox='0 0 {width} {height}' role='img' aria-label='K线与技术指标图'>",
             "<rect width='100%' height='100%' fill='#fff'/>"]
    for value in (low, (low + high) / 2, high):
        y = y_at(value)
        parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{width-right}' y2='{y:.1f}' class='grid'/><text x='{left-6}' y='{y+4:.1f}' text-anchor='end'>{value:.2f}</text>")
    candle_width = max(1.5, min(step * 0.62, 8))
    for index, bar in enumerate(shown):
        x = x_at(index)
        color = "#d92d20" if bar.close >= bar.open else "#079455"
        body_top, body_bottom = y_at(max(bar.open, bar.close)), y_at(min(bar.open, bar.close))
        parts.append(f"<line x1='{x:.1f}' y1='{y_at(bar.high):.1f}' x2='{x:.1f}' y2='{y_at(bar.low):.1f}' stroke='{color}'/>")
        parts.append(f"<rect x='{x-candle_width/2:.1f}' y='{body_top:.1f}' width='{candle_width:.1f}' height='{max(body_bottom-body_top,1):.1f}' fill='{color}'/>")
    for label_index, (period, color) in enumerate(((5, "#f79009"), (20, "#1570ef"), (60, "#7a5af8"))):
        points = " ".join(f"{x_at(i):.1f},{y_at(value):.1f}" for i, value in enumerate(ma_lines[period]) if not math.isnan(value))
        parts.append(f"<polyline points='{points}' fill='none' stroke='{color}' stroke-width='1.5'/><text x='{left+label_index*65}' y='16' fill='{color}'>MA{period}</text>")

    index_by_date = {bar.date: index for index, bar in enumerate(shown)}
    marker_groups: dict[tuple[object, str], list[str]] = {}
    for event in events:
        if event.date in index_by_date and event.direction != "neutral":
            marker_groups.setdefault((event.date, event.direction), []).append(event.name)
    for (event_date, direction), names in marker_groups.items():
        index = index_by_date[event_date]
        bullish = direction == "bullish"
        y = y_at(shown[index].low) + 12 if bullish else y_at(shown[index].high) - 10
        marker = "▲" if bullish else "▼"
        color = "#d92d20" if bullish else "#079455"
        title = html.escape("、".join(sorted(set(names))))
        parts.append(f"<text x='{x_at(index):.1f}' y='{y:.1f}' text-anchor='middle' fill='{color}' class='marker'><title>{title}</title>{marker}</text>")

    max_volume = max(bar.volume for bar in shown) or 1
    for index, bar in enumerate(shown):
        bar_height = bar.volume / max_volume * volume_height
        color = "#f97066" if bar.close >= bar.open else "#47cd89"
        parts.append(f"<rect x='{x_at(index)-candle_width/2:.1f}' y='{volume_top+volume_height-bar_height:.1f}' width='{candle_width:.1f}' height='{bar_height:.1f}' fill='{color}' opacity='.7'/>")
    parts.append(f"<text x='6' y='{volume_top+12}'>成交量</text>")

    dif, dea, histogram = macd(closes)
    macd_bound = max([abs(value) for value in dif + dea + histogram] + [1e-9])
    macd_y = lambda value: macd_top + macd_height / 2 - value / macd_bound * macd_height * .45
    parts.append(f"<line x1='{left}' y1='{macd_y(0):.1f}' x2='{width-right}' y2='{macd_y(0):.1f}' class='grid'/><text x='6' y='{macd_top+12}'>MACD</text>")
    for index, value in enumerate(histogram):
        y_zero, y_value = macd_y(0), macd_y(value)
        color = "#d92d20" if value >= 0 else "#079455"
        parts.append(f"<rect x='{x_at(index)-max(step*.28,1):.1f}' y='{min(y_zero,y_value):.1f}' width='{max(step*.56,1):.1f}' height='{max(abs(y_value-y_zero),.6):.1f}' fill='{color}'/>")
    for line, color in ((dif, "#f79009"), (dea, "#1570ef")):
        points = " ".join(f"{x_at(i):.1f},{macd_y(value):.1f}" for i, value in enumerate(line))
        parts.append(f"<polyline points='{points}' fill='none' stroke='{color}' stroke-width='1.2'/>")

    rsi_values = rsi(closes, 14)
    rsi_y = lambda value: rsi_top + (100-value) / 100 * rsi_height
    for level in (30, 70):
        parts.append(f"<line x1='{left}' y1='{rsi_y(level):.1f}' x2='{width-right}' y2='{rsi_y(level):.1f}' class='grid dashed'/><text x='{left-6}' y='{rsi_y(level)+4:.1f}' text-anchor='end'>{level}</text>")
    points = " ".join(f"{x_at(i):.1f},{rsi_y(value):.1f}" for i, value in enumerate(rsi_values) if not math.isnan(value))
    parts.append(f"<polyline points='{points}' fill='none' stroke='#7a5af8' stroke-width='1.4'/><text x='6' y='{rsi_top+12}'>RSI</text>")
    for index in range(0, len(shown), max(1, len(shown)//6)):
        parts.append(f"<text x='{x_at(index):.1f}' y='{height-5}' text-anchor='middle'>{shown[index].date.strftime('%m-%d')}</text>")
    parts.append("</svg>")
    return "".join(parts)
