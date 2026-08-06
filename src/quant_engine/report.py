from __future__ import annotations

import html
from datetime import date, timedelta
from pathlib import Path

from .charts import render_technical_chart
from .models import IndicatorReading, ScanResult, Signal


DIRECTION = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}


def write_reports(results: list[ScanResult], output_dir: str | Path, recent_days: int) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    md_path, html_path = output / "latest.md", output / "latest.html"
    md_path.write_text(render_markdown(results, recent_days), encoding="utf-8")
    html_path.write_text(render_html(results, recent_days), encoding="utf-8")
    return md_path, html_path


def render_markdown(results: list[ScanResult], recent_days: int) -> str:
    generated = max(result.as_of for result in results) if results else date.today()
    lines = ["# 每日技术信号报告", "", f"生成日期：{generated.isoformat()}", "",
             "> 信号是规则触发记录，不构成投资建议。", ""]
    if results:
        lines.extend(["## 标的列表", ""] +
                     [f"- {result.display_name or result.symbol}（{result.symbol}）：{result.last_close:.3f}，数据截止 {result.as_of}"
                      for result in results] + [""])
    for result in results:
        recent = _recent(result, recent_days, "1d")
        weekly = _recent_weeks(result, 8)
        new = [signal for signal in recent + weekly if signal.event_id in result.new_event_ids]
        lines.extend([f"## {result.display_name or result.symbol}（{result.symbol}）", "", f"数据源：{result.source_status or result.source}；数据截止：{result.as_of.isoformat()}",
                      f"数据质量：{result.data_quality.status if result.data_quality else '未检查'} — {result.data_quality.summary if result.data_quality else '无'}",
                      "", "### 本次首次发现", ""])
        if result.adjustment_notes:
            lines.extend(["", "### 行情口径调整", ""] + [f"- {note}" for note in result.adjustment_notes])
        if result.data_quality and result.data_quality.issues:
            lines.extend(["", "### 数据质量问题", ""] + [f"- {issue}" for issue in result.data_quality.issues])
        lines.extend(_markdown_signals(new) or ["- 无"])
        lines.extend(["", f"### 最近 {recent_days} 个自然日信号", ""])
        lines.extend(_markdown_signals(recent) or ["- 无"])
        lines.extend(["", "### 最近 8 周信号", ""])
        lines.extend(_markdown_signals(weekly) or ["- 无"])
        lines.extend(["", "### 日线当前状态", ""] + [f"- {state}" for state in result.states])
        lines.extend(["", "### 日线主流指标明细", "",
                      "| 类别 | 指标与参数 | 当前值 | 状态 | 依据 |",
                      "|---|---|---:|---|---|"] + _markdown_readings(result.indicator_readings or []))
        if result.forecast:
            forecast = result.forecast
            model_name = forecast.model.rsplit("/", 1)[-1]
            extreme_note = ("- 风险提示：预测幅度超过 15%，属于极端情景；在完成该标的历史样本外验证前，不应作为交易依据。"
                            if abs(forecast.end_return_pct) >= 15 else None)
            lines.extend(["", f"### {model_name} 预测辅助", "",
                          f"- {forecast.combined_view}",
                          f"- 未来 {len(forecast.points)} 个工作日末端收益中位数：{forecast.end_return_pct:+.2f}%",
                          f"- 多路径 10%–90% 区间：{forecast.end_return_low_pct:+.2f}% 至 {forecast.end_return_high_pct:+.2f}%",
                          f"- 上涨路径占比：{forecast.positive_path_ratio:.0%}（{forecast.path_count} 条采样路径）",
                          f"- 随机种子：{forecast.seed}；预测缓存：{'命中' if forecast.cache_hit else '新生成'}",
                          "- 这是概率情景，不是买卖信号；工作日日期未校正交易所节假日。"])
            if extreme_note:
                lines.append(extreme_note)
        lines.extend(["", "### 周线当前状态", ""] + [f"- {state}" for state in result.weekly_states] + [""])
        lines.extend(["### 周线主流指标明细", "",
                      "| 类别 | 指标与参数 | 当前值 | 状态 | 依据 |",
                      "|---|---|---:|---|---|"] + _markdown_readings(result.weekly_indicator_readings or []) + [""])
    return "\n".join(lines).rstrip() + "\n"


def render_html(results: list[ScanResult], recent_days: int) -> str:
    sections = []
    navigation = "".join(
        f"<a class='symbol-card' href='#{_anchor(result.symbol)}'><strong>{html.escape(result.display_name or result.symbol)}</strong>"
        f"<span>{html.escape(result.symbol)} · {result.last_close:.3f}</span><small>数据截止 {result.as_of}</small></a>"
        for result in results)
    for result in results:
        recent = _recent(result, recent_days, "1d")
        weekly = _recent_weeks(result, 8)
        new = [signal for signal in recent + weekly if signal.event_id in result.new_event_ids]
        states = "".join(f"<li>{html.escape(state)}</li>" for state in result.states)
        weekly_states = "".join(f"<li>{html.escape(state)}</li>" for state in result.weekly_states)
        chart_events = [signal for signal in result.events if signal.timeframe == "1d"]
        daily_chart = render_technical_chart(result.bars, chart_events)
        weekly_chart = render_technical_chart(result.weekly_bars, weekly)
        forecast_html = _forecast_html(result)
        daily_readings = _html_readings(result.indicator_readings or [])
        weekly_readings = _html_readings(result.weekly_indicator_readings or [])
        quality = result.data_quality
        quality_class = "quality-ok" if quality and quality.status == "正常" else "quality-warn" if quality and quality.analyzable else "quality-stop"
        issues_html = "" if not quality or not quality.issues else "<ul>" + "".join(f"<li>{html.escape(issue)}</li>" for issue in quality.issues) + "</ul>"
        quality_html = (f"<div class='quality {quality_class}'><strong>数据质量：{html.escape(quality.status)}</strong>"
                        f"<span>{html.escape(quality.summary)}</span>{issues_html}</div>") if quality else ""
        adjustments_html = "" if not result.adjustment_notes else (
            "<div class='adjustments'><strong>行情口径调整</strong><ul>" +
            "".join(f"<li>{html.escape(note)}</li>" for note in result.adjustment_notes) + "</ul></div>")
        sections.append(f"<section id='{_anchor(result.symbol)}'><div class='section-title'><h2>{html.escape(result.display_name or result.symbol)}"
                        f" <span>{html.escape(result.symbol)}</span></h2><a href='#top'>返回顶部 ↑</a></div>"
                        f"<p class='meta'>数据源：{html.escape(result.source_status or result.source)}；数据截止：{result.as_of}</p>{quality_html}{adjustments_html}"
                        f"<h3>本次首次发现</h3>{_html_signals(new)}"
                        f"<h3>最近 {recent_days} 个自然日信号</h3>{_html_signals(recent)}"
                        f"<h3>日线图（最近 120 根）</h3>{daily_chart}"
                        f"<h3>日线当前状态</h3><ul>{states}</ul>"
                        f"<h3>日线主流指标明细</h3>{daily_readings}"
                        f"{forecast_html}"
                        f"<h3>最近 8 周信号</h3>{_html_signals(weekly)}"
                        f"<h3>周线图（最近 120 根）</h3>{weekly_chart}"
                        f"<h3>周线当前状态</h3><ul>{weekly_states}</ul>"
                        f"<h3>周线主流指标明细</h3>{weekly_readings}</section>")
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>每日技术信号报告</title>
<style>html{scroll-behavior:smooth;scroll-padding-top:16px}body{font:16px/1.65 system-ui,sans-serif;max-width:980px;margin:32px auto;padding:0 20px;color:#202124}
h1,h2,h3{line-height:1.25}section{border-top:1px solid #ddd;padding:18px 0}.meta,.note{color:#666}
.bullish{color:#b42318}.bearish{color:#067647}.neutral{color:#475467}li{margin:.35em 0}
.chart{display:block;width:100%;height:auto;border:1px solid #e4e7ec;border-radius:8px}.chart text{font:11px system-ui,sans-serif;fill:#667085}
.chart .grid{stroke:#e4e7ec;stroke-width:1}.chart .dashed{stroke-dasharray:4 4}.chart .marker{font-size:12px;font-weight:700}
table{border-collapse:collapse;margin:12px 0;width:100%}th,td{border-bottom:1px solid #e4e7ec;padding:7px;text-align:right}th:first-child,td:first-child{text-align:left}
.table-scroll{overflow-x:auto}.readings{font-size:14px;min-width:900px}.readings th,.readings td{text-align:left;vertical-align:top}.readings small{display:block;color:#667085;max-width:210px}
.symbol-nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:18px 0 32px}.symbol-card{border:1px solid #d0d5dd;border-radius:10px;padding:12px 14px;text-decoration:none;color:#101828;background:#f9fafb}.symbol-card:hover{border-color:#175cd3;background:#eff4ff}.symbol-card span,.symbol-card small{display:block;color:#667085}.section-title{display:flex;align-items:center;justify-content:space-between;gap:16px}.section-title h2 span{font-size:.7em;color:#667085;font-weight:500}.section-title a{white-space:nowrap;font-size:14px}
.quality,.adjustments,.forecast-warning{border-radius:8px;padding:10px 12px;margin:10px 0}.quality strong,.quality span{display:block}.quality-ok{background:#ecfdf3;color:#067647}.quality-warn{background:#fffaeb;color:#93370d}.quality-stop{background:#fef3f2;color:#b42318}.adjustments{background:#eff8ff;color:#175cd3}.adjustments ul{margin:.3em 0}.forecast-warning{background:#fff4ed;color:#b93815}</style></head><body id="top">
<h1>每日技术信号报告</h1><p class="note">信号是规则触发记录，不构成投资建议。</p>
<nav class="symbol-nav" aria-label="标的导航">""" + navigation + "</nav>" + "".join(sections) + "</body></html>"


def _recent(result: ScanResult, days: int, timeframe: str) -> list[Signal]:
    threshold = result.as_of - timedelta(days=max(days - 1, 0))
    return [signal for signal in result.events if signal.timeframe == timeframe and signal.date >= threshold]


def _anchor(symbol: str) -> str:
    return "symbol-" + "".join(character for character in symbol.lower() if character.isalnum() or character in "-_")


def _recent_weeks(result: ScanResult, weeks: int) -> list[Signal]:
    dates = {bar.date for bar in result.weekly_bars[-weeks:]}
    return [signal for signal in result.events if signal.timeframe == "1w" and signal.date in dates]


def _markdown_signals(signals: list[Signal]) -> list[str]:
    return [f"- {signal.date.isoformat()} [{signal.timeframe} / {DIRECTION[signal.direction]}] {signal.name}：{signal.detail}"
            for signal in sorted(signals, key=lambda item: item.date, reverse=True)]


def _html_signals(signals: list[Signal]) -> str:
    if not signals:
        return "<p>无</p>"
    items = "".join(f"<li class='{signal.direction}'>{signal.date} [{signal.timeframe} / {DIRECTION[signal.direction]}] "
                    f"<strong>{html.escape(signal.name)}</strong>：{html.escape(signal.detail)}</li>"
                    for signal in sorted(signals, key=lambda item: item.date, reverse=True))
    return f"<ul>{items}</ul>"


def _markdown_readings(readings: list[IndicatorReading]) -> list[str]:
    return [f"| {item.category} | {item.indicator}（{item.parameters}） | {item.values} | {DIRECTION[item.direction]} · {item.status} | {item.rationale} |"
            for item in readings]


def _html_readings(readings: list[IndicatorReading]) -> str:
    if not readings:
        return "<p>无</p>"
    rows = "".join(
        f"<tr><td>{html.escape(item.category)}</td><td><strong>{html.escape(item.indicator)}</strong>"
        f"<small>{html.escape(item.parameters)}</small></td><td>{html.escape(item.values)}</td>"
        f"<td class='{item.direction}'>{DIRECTION[item.direction]} · {html.escape(item.status)}</td>"
        f"<td>{html.escape(item.rationale)}</td></tr>" for item in readings)
    return ("<div class='table-scroll'><table class='readings'><thead><tr><th>类别</th><th>指标与参数</th>"
            "<th>当前值</th><th>状态</th><th>依据</th></tr></thead><tbody>" + rows + "</tbody></table></div>")


def _forecast_html(result: ScanResult) -> str:
    forecast = result.forecast
    if not forecast or not forecast.points:
        return ""
    rows = "".join(
        f"<tr><td>{point.date}</td><td>{point.close:.2f}</td>"
        f"<td>{point.close_low:.2f}–{point.close_high:.2f}</td></tr>"
        for point in forecast.points
    )
    values = [result.last_close] + [point.close_low for point in forecast.points] + [point.close_high for point in forecast.points]
    low, high = min(values), max(values)
    padding = max((high - low) * .12, abs(high) * .002)
    low, high = low - padding, high + padding
    width, height, left, right = 960, 260, 65, 25
    x_step = (width - left - right) / len(forecast.points)
    x_at = lambda index: left + index * x_step
    y_at = lambda value: 20 + (high - value) / (high - low) * 190
    median = [(0, result.last_close)] + [(index + 1, point.close) for index, point in enumerate(forecast.points)]
    polygon = [(0, result.last_close)] + [(index + 1, point.close_high) for index, point in enumerate(forecast.points)]
    polygon += [(index + 1, point.close_low) for index, point in reversed(list(enumerate(forecast.points)))]
    polygon_points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in polygon)
    median_points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in median)
    svg = [f"<svg class='chart forecast' viewBox='0 0 {width} {height}' role='img' aria-label='Kronos预测路径'>",
           "<rect width='100%' height='100%' fill='#fff'/>",
           f"<polygon points='{polygon_points}' fill='#84adff' opacity='.25'/>",
           f"<polyline points='{median_points}' fill='none' stroke='#175cd3' stroke-width='2.5'/>",
           f"<line x1='{left}' y1='{y_at(result.last_close):.1f}' x2='{width-right}' y2='{y_at(result.last_close):.1f}' class='grid dashed'/>"]
    for index, point in enumerate(forecast.points, 1):
        svg.append(f"<text x='{x_at(index):.1f}' y='238' text-anchor='middle'>{point.date.strftime('%m-%d')}</text>")
    svg.append(f"<text x='6' y='{y_at(high)+4:.1f}'>{high:.2f}</text><text x='6' y='{y_at(low)+4:.1f}'>{low:.2f}</text></svg>")
    model_name = forecast.model.rsplit("/", 1)[-1]
    extreme = ("<p class='forecast-warning'><strong>极端预测：</strong>五日中位幅度超过 15%。"
               "在完成该标的历史样本外验证前，不应作为交易依据。</p>"
               if abs(forecast.end_return_pct) >= 15 else "")
    return (f"<h3>{html.escape(model_name)} 预测辅助</h3><p><strong>{html.escape(forecast.combined_view)}</strong></p>"
            f"<p>未来 {len(forecast.points)} 个工作日末端收益中位数 <strong>{forecast.end_return_pct:+.2f}%</strong>；"
            f"多路径 10%–90% 区间 {forecast.end_return_low_pct:+.2f}% 至 {forecast.end_return_high_pct:+.2f}%；"
            f"上涨路径占比 {forecast.positive_path_ratio:.0%}（{forecast.path_count} 条路径）。</p>"
            + extreme + "".join(svg) + f"<table><thead><tr><th>日期</th><th>中位收盘</th><th>路径区间</th></tr></thead><tbody>{rows}</tbody></table>"
            f"<p class='note'>模型：{html.escape(forecast.model)}；输入 {forecast.lookback} 根日线；随机种子 {forecast.seed}；"
            f"预测缓存{'命中' if forecast.cache_hit else '新生成'}。预测是概率情景，不是买卖信号；日期按工作日生成，未校正交易所节假日。</p>")
