from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .scanner import SignalSettings


@dataclass
class KronosSettings:
    enabled: bool = False
    model: str = "NeoQuasar/Kronos-small"
    tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base"
    lookback: int = 400
    prediction_days: int = 5
    path_count: int = 20
    seed: int = 20260726
    temperature: float = 0.8
    top_p: float = 0.9
    device: str | None = None


@dataclass(frozen=True)
class SplitAdjustment:
    effective_date: str
    ratio: float
    description: str = "份额拆分"


@dataclass
class AppConfig:
    symbols: list[str] = field(default_factory=lambda: ["sh000001"])
    provider: str = "eastmoney"
    csv_dir: str = "market_data"
    data_dir: str = "daily_signal_data"
    settings: SignalSettings = field(default_factory=SignalSettings)
    kronos: KronosSettings = field(default_factory=KronosSettings)
    adjustments: dict[str, list[SplitAdjustment]] = field(default_factory=dict)


def load_config(path: str | Path | None) -> AppConfig:
    if path is None:
        return AppConfig()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    signal_raw = raw.pop("signals", {})
    kronos_raw = raw.pop("kronos", {})
    adjustment_raw = raw.pop("adjustments", {})
    if "ma_pairs" in signal_raw:
        signal_raw["ma_pairs"] = [tuple(pair) for pair in signal_raw["ma_pairs"]]
    adjustments = {symbol: [SplitAdjustment(**item) for item in items]
                   for symbol, items in adjustment_raw.items()}
    return AppConfig(settings=SignalSettings(**signal_raw), kronos=KronosSettings(**kronos_raw),
                     adjustments=adjustments, **raw)
