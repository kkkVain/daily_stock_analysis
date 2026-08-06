from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cache import CachedProvider
from .adjustments import apply_split_adjustments
from .config import AppConfig, load_config
from .history import SignalHistory
from .models import ScanResult
from .names import SymbolNameResolver
from .kronos import KronosForecaster
from .patterns import scan_graphical_patterns
from .quality import assess_data_quality
from .providers import CsvProvider, EastMoneyProvider, FallbackProvider, SinaProvider
from .report import write_reports
from .export import results_to_dict
from .readings import build_indicator_readings
from .scanner import scan_symbol
from .timeframes import confirmed_weekly_bars


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="扫描少量标的最近出现的技术信号")
    parser.add_argument("--config", help="JSON 配置文件", default=None)
    parser.add_argument("--symbols", nargs="+", help="覆盖配置中的代码，例如 sh000001 sz399006")
    parser.add_argument("--provider", choices=("eastmoney", "csv"), help="覆盖行情数据源")
    parser.add_argument("--csv-dir", help="CSV 数据目录，每个代码一个 <symbol>.csv")
    parser.add_argument("--data-dir", help="缓存、历史和报告目录")
    parser.add_argument("--json-output", help="把标准化分析结果写入 JSON 文件")
    parser.add_argument("--machine-only", action="store_true", help="仅输出JSON，不改写HTML/Markdown和信号历史")
    return parser


def run(config: AppConfig, *, persist_outputs: bool = True) -> tuple[list[ScanResult], Path | None, Path | None]:
    data_dir = Path(config.data_dir)
    if config.provider == "eastmoney":
        provider = CachedProvider(FallbackProvider(EastMoneyProvider(), SinaProvider()), data_dir / "cache")
    elif config.provider == "csv":
        provider = CsvProvider(config.csv_dir)
    else:
        raise ValueError(f"unsupported provider: {config.provider}")

    history = SignalHistory(data_dir / "signals.csv")
    name_resolver = SymbolNameResolver(data_dir / "symbol_names.json")
    forecaster = None
    if config.kronos.enabled:
        forecaster = KronosForecaster(config.kronos, data_dir / "runtime" / "Kronos", data_dir / "forecasts")
    results: list[ScanResult] = []
    pending = []
    for symbol in config.symbols:
        bars = provider.daily_bars(symbol)
        bars, adjustment_notes = apply_split_adjustments(bars, config.adjustments.get(symbol, []))
        quality = assess_data_quality(bars)
        weekly_bars = confirmed_weekly_bars(bars) if quality.analyzable else []
        if quality.analyzable:
            daily_events, states = scan_symbol(symbol, bars, config.settings)
            graphical_events, graphical_states = scan_graphical_patterns(symbol, bars)
            weekly_events, weekly_states = scan_symbol(symbol, weekly_bars, config.settings, "1w")
            events = daily_events + graphical_events + weekly_events
            states.extend(graphical_states)
        else:
            events, states, weekly_states = [], [], []
        new_ids = history.classify_new(events) if persist_outputs else set()
        forecast = forecaster.forecast(symbol, bars, events) if forecaster and quality.analyzable else None
        readings = build_indicator_readings(bars) if quality.analyzable else []
        weekly_readings = build_indicator_readings(weekly_bars, "1w") if quality.analyzable else []
        display_name = name_resolver.resolve(symbol)
        source_status = getattr(provider, "last_status", provider.name)
        results.append(ScanResult(symbol, bars[-1].date, bars[-1].close, events, new_ids, states,
                                  provider.name, bars, weekly_bars, weekly_states, forecast, readings, weekly_readings,
                                  display_name, quality, source_status, adjustment_notes))
        pending.extend(events)

    if persist_outputs:
        md_path, html_path = write_reports(results, data_dir / "reports", config.settings.recent_days)
        history.append(pending)
    else:
        md_path, html_path = None, None
    return results, md_path, html_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.symbols:
        config.symbols = args.symbols
    if args.provider:
        config.provider = args.provider
    if args.csv_dir:
        config.csv_dir = args.csv_dir
    if args.data_dir:
        config.data_dir = args.data_dir
    try:
        results, md_path, html_path = run(config, persist_outputs=not args.machine_only)
    except Exception as exc:
        print(f"扫描失败: {exc}", file=sys.stderr)
        return 1
    new_count = sum(len(result.new_event_ids) for result in results)
    print(f"扫描完成：{len(results)} 个标的，本次首次记录 {new_count} 个历史事件")
    if md_path and html_path:
        print(f"Markdown: {md_path.resolve()}")
        print(f"HTML: {html_path.resolve()}")
    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(results_to_dict(results, config.settings.recent_days), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output_path)
        print(f"JSON: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
