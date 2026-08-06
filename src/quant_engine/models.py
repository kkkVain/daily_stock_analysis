from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .quality import DataQuality


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    date: date
    name: str
    direction: str
    detail: str
    value: float | None = None
    timeframe: str = "1d"

    @property
    def event_id(self) -> str:
        return "|".join((self.symbol, self.timeframe, self.name, self.direction, self.date.isoformat()))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["date"] = self.date.isoformat()
        value["event_id"] = self.event_id
        return value


@dataclass
class ScanResult:
    symbol: str
    as_of: date
    last_close: float
    events: list[Signal]
    new_event_ids: set[str]
    states: list[str]
    source: str
    bars: list[Bar]
    weekly_bars: list[Bar]
    weekly_states: list[str]
    forecast: ForecastResult | None = None
    indicator_readings: list[IndicatorReading] | None = None
    weekly_indicator_readings: list[IndicatorReading] | None = None
    display_name: str | None = None
    data_quality: DataQuality | None = None
    source_status: str | None = None
    adjustment_notes: list[str] | None = None


@dataclass(frozen=True)
class IndicatorReading:
    category: str
    indicator: str
    parameters: str
    values: str
    status: str
    direction: str
    rationale: str


@dataclass
class ForecastPoint:
    date: date
    open: float
    high: float
    low: float
    close: float
    close_low: float
    close_high: float


@dataclass
class ForecastResult:
    model: str
    lookback: int
    path_count: int
    points: list[ForecastPoint]
    end_return_pct: float
    end_return_low_pct: float
    end_return_high_pct: float
    positive_path_ratio: float
    abu_bias: str
    combined_view: str
    seed: int | None = None
    cache_hit: bool = False
