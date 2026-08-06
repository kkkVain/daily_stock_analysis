from __future__ import annotations

import csv
import io
import json
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path

from .models import Bar


class DataProvider(ABC):
    name = "unknown"

    @abstractmethod
    def daily_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        raise NotImplementedError


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unsupported date: {value}")


class CsvProvider(DataProvider):
    """Read OHLCV data from ``<data_dir>/<symbol>.csv``.

    Column names are case-insensitive. ``date,open,high,low,close`` are
    required and ``volume`` is optional. ABU's unnamed date index is accepted.
    """

    name = "csv"

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def daily_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        path = self.data_dir / f"{symbol}.csv"
        if not path.exists():
            raise FileNotFoundError(f"行情文件不存在: {path}")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        bars: list[Bar] = []
        for raw in rows:
            row = {(key or "index").strip().lower(): (value or "").strip() for key, value in raw.items()}
            date_value = row.get("date") or row.get("index")
            if not date_value:
                continue
            bar_date = _parse_date(date_value)
            if start and bar_date < start or end and bar_date > end:
                continue
            bars.append(Bar(bar_date, float(row["open"]), float(row["high"]),
                            float(row["low"]), float(row["close"]), float(row.get("volume") or 0)))
        return _clean_bars(bars)


class EastMoneyProvider(DataProvider):
    """Eastmoney public daily K-line endpoint for mainland stocks and indices."""

    name = "eastmoney"
    endpoint = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    @staticmethod
    def _secid(symbol: str) -> str:
        code = symbol.lower().strip()
        if code.startswith("sh") and code[2:].isdigit():
            return f"1.{code[2:]}"
        if code.startswith("sz") and code[2:].isdigit():
            return f"0.{code[2:]}"
        raise ValueError(f"东方财富数据源要求 sh/sz 代码，例如 sh000001；收到 {symbol}")

    def daily_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        params = {
            "secid": self._secid(symbol), "klt": "101", "fqt": "1",
            "beg": (start or date(1990, 1, 1)).strftime("%Y%m%d"),
            "end": (end or date.today()).strftime("%Y%m%d"),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        }
        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 daily-signal/0.1"})
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = json.load(io.TextIOWrapper(response, encoding="utf-8"))
                data = payload.get("data")
                if not data or not data.get("klines"):
                    raise RuntimeError(f"未取得 {symbol} 行情")
                bars = []
                for line in data["klines"]:
                    fields = line.split(",")
                    bars.append(Bar(_parse_date(fields[0]), float(fields[1]), float(fields[3]),
                                    float(fields[4]), float(fields[2]), float(fields[5])))
                return _clean_bars(bars)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
        raise RuntimeError(f"获取 {symbol} 行情失败: {last_error}") from last_error


class SinaProvider(DataProvider):
    """Sina daily K-line endpoint for mainland stocks and indices."""

    name = "sina"
    endpoint = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"

    def daily_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        code = symbol.lower().strip()
        if not (len(code) == 8 and code[:2] in ("sh", "sz") and code[2:].isdigit()):
            raise ValueError(f"新浪数据源要求 sh/sz 代码，例如 sh000001；收到 {symbol}")
        params = {"symbol": code, "scale": "240", "ma": "no", "datalen": "1023"}
        request = urllib.request.Request(
            f"{self.endpoint}?{urllib.parse.urlencode(params)}",
            headers={"User-Agent": "Mozilla/5.0 daily-signal/0.1", "Referer": "https://finance.sina.com.cn/"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(io.TextIOWrapper(response, encoding="utf-8"))
        if not isinstance(payload, list) or not payload:
            raise RuntimeError(f"未取得 {symbol} 行情")
        bars = [Bar(_parse_date(row["day"]), float(row["open"]), float(row["high"]),
                    float(row["low"]), float(row["close"]), float(row.get("volume") or 0))
                for row in payload]
        return [bar for bar in _clean_bars(bars)
                if (not start or bar.date >= start) and (not end or bar.date <= end)]


class FallbackProvider(DataProvider):
    """Try providers in order and report the provider that most recently succeeded."""

    def __init__(self, *providers: DataProvider):
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.name = "+".join(provider.name for provider in providers)
        self.last_provider = self.name

    def daily_bars(self, symbol: str, start: date | None = None, end: date | None = None) -> list[Bar]:
        errors = []
        for provider in self.providers:
            try:
                bars = provider.daily_bars(symbol, start, end)
                self.last_provider = provider.name
                return bars
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError(f"获取 {symbol} 行情失败（{'；'.join(errors)}）")


def _clean_bars(bars: list[Bar]) -> list[Bar]:
    by_date = {bar.date: bar for bar in bars if bar.high >= bar.low and bar.close > 0}
    return [by_date[key] for key in sorted(by_date)]
