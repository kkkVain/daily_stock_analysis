from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .models import Bar
from .providers import DataProvider, _clean_bars


class CachedProvider(DataProvider):
    name = "cache"

    def __init__(self, provider: DataProvider, cache_dir: str | Path):
        self.provider = provider
        self.cache_dir = Path(cache_dir)
        self.name = f"{provider.name}+cache"
        self.last_source = "unknown"
        self.last_status = "尚未读取"

    def daily_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        cached = self._read(symbol)
        try:
            # Always refresh one coherent adjusted history. Incrementally joining
            # old and new forward-adjusted data can create false split gaps when
            # the adjustment basis changes.
            fresh = self.provider.daily_bars(symbol, start, end)
            merged = _clean_bars(fresh)
            if not merged:
                raise RuntimeError(f"{symbol} 全量行情为空")
            self.last_source = getattr(self.provider, "last_provider", self.provider.name)
            self.last_status = f"联网全量刷新（{self.last_source}）"
            self._write(symbol, merged)
        except Exception as exc:
            if not cached:
                raise
            merged = cached
            self.last_source = "cache"
            self.last_status = f"联网失败，使用缓存（{cached[-1].date}；{type(exc).__name__}）"
        return [bar for bar in merged if (not start or bar.date >= start) and (not end or bar.date <= end)]

    def _path(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol}.csv"

    def _read(self, symbol: str) -> list[Bar]:
        path = self._path(symbol)
        if not path.exists():
            return []
        with path.open(encoding="utf-8", newline="") as handle:
            return [Bar(date.fromisoformat(row["date"]), float(row["open"]), float(row["high"]),
                        float(row["low"]), float(row["close"]), float(row["volume"]))
                    for row in csv.DictReader(handle)]

    def _write(self, symbol: str, bars: list[Bar]) -> None:
        path = self._path(symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("date", "open", "high", "low", "close", "volume"))
            for bar in bars:
                writer.writerow((bar.date.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume))
        temp.replace(path)
