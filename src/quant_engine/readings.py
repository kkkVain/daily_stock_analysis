from __future__ import annotations

import math

from .indicators import (atr, bollinger, cci, dmi_adx, ema, macd, obv, roc, rsi,
                         sma, stochastic_kdj, supertrend)
from .models import Bar, IndicatorReading


def build_indicator_readings(bars: list[Bar], timeframe: str = "1d") -> list[IndicatorReading]:
    """Return transparent current readings using common, fixed parameters."""
    if len(bars) < 61:
        return [IndicatorReading("数据", "样本长度", "至少 61 根", f"当前 {len(bars)} 根",
                                 "不足", "neutral", "无法稳定计算 EMA60 等长周期指标")]
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    label = "周线" if timeframe == "1w" else "日线"
    rows: list[IndicatorReading] = []

    ema_lines = {period: ema(closes, period) for period in (5, 10, 20, 60)}
    ema_values = [ema_lines[period][-1] for period in (5, 10, 20, 60)]
    if ema_values == sorted(ema_values, reverse=True):
        ema_status, ema_direction = "多头排列", "bullish"
    elif ema_values == sorted(ema_values):
        ema_status, ema_direction = "空头排列", "bearish"
    else:
        ema_status, ema_direction = "交错排列", "neutral"
    slope20 = (ema_lines[20][-1] / ema_lines[20][-6] - 1) * 100
    slope60 = (ema_lines[60][-1] / ema_lines[60][-6] - 1) * 100
    rows.append(_row("趋势", "EMA 排列", "EMA(5,10,20,60)；斜率比较 5 期",
                     " / ".join(f"{value:.3f}" for value in ema_values), ema_status, ema_direction,
                     f"EMA20 近 5 期 {slope20:+.2f}%，EMA60 {slope60:+.2f}%"))

    plus_di, minus_di, adx_line = dmi_adx(highs, lows, closes, 14)
    trend_strength = "强趋势" if adx_line[-1] >= 25 else "趋势形成中" if adx_line[-1] >= 20 else "弱趋势/震荡"
    dmi_direction = "bullish" if plus_di[-1] > minus_di[-1] else "bearish"
    rows.append(_row("趋势", "DMI / ADX", "Wilder(14)；ADX≥25 为强趋势",
                     f"+DI {plus_di[-1]:.2f} / -DI {minus_di[-1]:.2f} / ADX {adx_line[-1]:.2f}",
                     f"{trend_strength}，{'多方' if dmi_direction == 'bullish' else '空方'}占优",
                     dmi_direction if adx_line[-1] >= 20 else "neutral",
                     "ADX 只表示趋势强度；方向由 +DI 与 -DI 比较"))

    st_line, st_direction = supertrend(highs, lows, closes, 10, 3.0)
    st_bullish = st_direction[-1] > 0
    rows.append(_row("趋势", "SuperTrend", "ATR(10) × 3",
                     f"线 {st_line[-1]:.3f} / 收盘 {closes[-1]:.3f}",
                     "多头状态" if st_bullish else "空头状态", "bullish" if st_bullish else "bearish",
                     f"价格位于 SuperTrend {'上方' if st_bullish else '下方'}"))

    dif, dea, histogram = macd(closes, 12, 26, 9)
    macd_direction = "bullish" if dif[-1] > dea[-1] else "bearish"
    rows.append(_row("动量", "MACD", "EMA(12,26,9)；柱值=2×(DIF-DEA)",
                     f"DIF {dif[-1]:.4f} / DEA {dea[-1]:.4f} / 柱 {histogram[-1]:+.4f}",
                     "DIF 高于 DEA" if macd_direction == "bullish" else "DIF 低于 DEA", macd_direction,
                     f"柱体较前一期{'增强' if abs(histogram[-1]) > abs(histogram[-2]) else '收敛'}"))

    rsi_line = rsi(closes, 14)
    rsi_value = rsi_line[-1]
    rsi_status = "超买区" if rsi_value >= 70 else "超卖区" if rsi_value <= 30 else "中性偏强" if rsi_value >= 50 else "中性偏弱"
    rsi_direction = "bullish" if 50 <= rsi_value < 70 else "bearish" if 30 < rsi_value < 50 else "neutral"
    rows.append(_row("动量", "RSI", "Wilder RSI(14)；30/50/70", f"{rsi_value:.2f}",
                     rsi_status, rsi_direction, "超买/超卖描述位置，不单独等同于反转信号"))

    k, d, j = stochastic_kdj(highs, lows, closes, 9, 3, 3)
    kdj_direction = "bullish" if k[-1] > d[-1] else "bearish"
    zone = "超买区" if k[-1] >= 80 and d[-1] >= 80 else "超卖区" if k[-1] <= 20 and d[-1] <= 20 else "中性区"
    rows.append(_row("动量", "KDJ", "(9,3,3)；20/80", f"K {k[-1]:.2f} / D {d[-1]:.2f} / J {j[-1]:.2f}",
                     f"{zone}，K {'高于' if kdj_direction == 'bullish' else '低于'} D", kdj_direction,
                     "仅在超卖金叉或超买死叉时作为较强择时提示"))

    cci_line = cci(highs, lows, closes, 20)
    cci_value = cci_line[-1]
    cci_status = "强势区" if cci_value >= 100 else "弱势区" if cci_value <= -100 else "常态区"
    cci_direction = "bullish" if cci_value >= 100 else "bearish" if cci_value <= -100 else "neutral"
    rows.append(_row("动量", "CCI", "CCI(20)；±100", f"{cci_value:.2f}", cci_status, cci_direction,
                     "突破 +100/-100 用于识别动量进入强势/弱势区"))

    roc_line = roc(closes, 12)
    roc_value = roc_line[-1]
    rows.append(_row("动量", "ROC", "ROC(12)", f"{roc_value:+.2f}%",
                     "正动量" if roc_value > 0 else "负动量", "bullish" if roc_value > 0 else "bearish",
                     f"当前收盘相对 12 {label}前变化 {roc_value:+.2f}%"))

    atr_line = atr(highs, lows, closes, 14)
    atr_pct = atr_line[-1] / closes[-1] * 100
    valid_atr = [value / close * 100 for value, close in zip(atr_line, closes) if not math.isnan(value) and close][-252:]
    percentile = 100 * sum(value <= atr_pct for value in valid_atr) / len(valid_atr)
    atr_change = (atr_line[-1] / atr_line[-6] - 1) * 100
    volatility = "高波动" if percentile >= 75 else "低波动" if percentile <= 25 else "常态波动"
    rows.append(_row("波动", "ATR", "Wilder ATR(14)；近 252 期百分位",
                     f"{atr_line[-1]:.4f} / ATR% {atr_pct:.2f}% / P{percentile:.0f}", volatility, "neutral",
                     f"ATR 近 5 期 {atr_change:+.2f}%；ATR 不判断涨跌方向"))

    middle, upper, lower = bollinger(closes, 20, 2.0)
    boll_status = "上轨上方" if closes[-1] > upper[-1] else "下轨下方" if closes[-1] < lower[-1] else "中轨上方" if closes[-1] >= middle[-1] else "中轨下方"
    boll_direction = "bullish" if closes[-1] >= middle[-1] else "bearish"
    rows.append(_row("波动/位置", "Bollinger", "SMA(20) ± 2σ",
                     f"下 {lower[-1]:.3f} / 中 {middle[-1]:.3f} / 上 {upper[-1]:.3f}", boll_status, boll_direction,
                     f"收盘 {closes[-1]:.3f} 位于{boll_status}"))

    previous_high20, previous_low20 = max(highs[-21:-1]), min(lows[-21:-1])
    donchian_status = "向上突破" if closes[-1] > previous_high20 else "向下突破" if closes[-1] < previous_low20 else "通道内"
    donchian_direction = "bullish" if donchian_status == "向上突破" else "bearish" if donchian_status == "向下突破" else "neutral"
    rows.append(_row("突破", "Donchian", "前 20 期最高/最低（不含当期）",
                     f"下沿 {previous_low20:.3f} / 上沿 {previous_high20:.3f}", donchian_status, donchian_direction,
                     f"收盘 {closes[-1]:.3f}{'未突破通道' if donchian_direction == 'neutral' else '完成突破'}"))

    kel_mid = ema(closes, 20)
    kel_atr = atr(highs, lows, closes, 20)
    kel_upper, kel_lower = kel_mid[-1] + 2 * kel_atr[-1], kel_mid[-1] - 2 * kel_atr[-1]
    kel_status = "上轨上方" if closes[-1] > kel_upper else "下轨下方" if closes[-1] < kel_lower else "通道中轴上方" if closes[-1] >= kel_mid[-1] else "通道中轴下方"
    rows.append(_row("波动/位置", "Keltner", "EMA(20) ± 2×Wilder ATR(20)",
                     f"下 {kel_lower:.3f} / 中 {kel_mid[-1]:.3f} / 上 {kel_upper:.3f}", kel_status,
                     "bullish" if closes[-1] >= kel_mid[-1] else "bearish", f"收盘 {closes[-1]:.3f} 位于{kel_status}"))

    obv_line = obv(closes, volumes)
    obv_ma = ema(obv_line, 20)
    obv_direction = "bullish" if obv_line[-1] > obv_ma[-1] else "bearish"
    rows.append(_row("成交量", "OBV", "OBV；信号线 EMA(20)",
                     f"OBV {_compact(obv_line[-1])} / EMA20 {_compact(obv_ma[-1])}",
                     "资金量能偏强" if obv_direction == "bullish" else "资金量能偏弱", obv_direction,
                     f"OBV 位于其 EMA20 {'上方' if obv_direction == 'bullish' else '下方'}"))

    volume_ma20 = sma(volumes, 20)[-1]
    ratio = volumes[-1] / volume_ma20 if volume_ma20 else 0
    volume_status = "明显放量" if ratio >= 1.5 else "缩量" if ratio <= .7 else "正常量"
    rows.append(_row("成交量", "成交量相对均量", "当期量 / SMA(20)", f"{ratio:.2f} 倍", volume_status, "neutral",
                     "成交量本身不判断方向，需结合价格和突破位置"))
    return rows


def _row(category: str, indicator: str, parameters: str, values: str, status: str,
         direction: str, rationale: str) -> IndicatorReading:
    return IndicatorReading(category, indicator, parameters, values, status, direction, rationale)


def _compact(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value:.0f}"
