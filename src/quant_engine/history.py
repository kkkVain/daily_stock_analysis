from __future__ import annotations

import csv
from pathlib import Path

from .models import Signal


FIELDS = ("event_id", "symbol", "date", "timeframe", "name", "direction", "detail", "value")


class SignalHistory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.known_ids = self._load_ids()

    def classify_new(self, signals: list[Signal]) -> set[str]:
        return {signal.event_id for signal in signals if signal.event_id not in self.known_ids}

    def append(self, signals: list[Signal]) -> None:
        fresh_by_id = {signal.event_id: signal for signal in signals if signal.event_id not in self.known_ids}
        fresh = list(fresh_by_id.values())
        if not fresh:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.path.exists()
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            if write_header:
                writer.writeheader()
            for signal in fresh:
                row = signal.to_dict()
                writer.writerow({field: row.get(field) for field in FIELDS})
                self.known_ids.add(signal.event_id)

    def _load_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        with self.path.open(encoding="utf-8", newline="") as handle:
            return {row["event_id"] for row in csv.DictReader(handle)}
