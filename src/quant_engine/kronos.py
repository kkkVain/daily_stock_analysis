from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date
from pathlib import Path

from .config import KronosSettings
from .models import Bar, ForecastPoint, ForecastResult, Signal


class KronosForecaster:
    """Thin adapter around the official Kronos inference implementation."""

    def __init__(self, settings: KronosSettings, runtime_dir: str | Path, cache_dir: str | Path):
        self.settings = settings
        self.cache_dir = Path(cache_dir)
        runtime = Path(runtime_dir).resolve()
        if (runtime / "model" / "kronos.py").exists():
            # Keep the former external-runtime mode available for custom forks.
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "dsa_external_kronos_model",
                runtime / "model" / "__init__.py",
                submodule_search_locations=[str(runtime / "model")],
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(f"无法加载 Kronos 运行库：{runtime}")
            module = importlib.util.module_from_spec(spec)
            import sys
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        else:
            from .kronos_runtime import model as module
        tokenizer = module.KronosTokenizer.from_pretrained(settings.tokenizer)
        model = module.Kronos.from_pretrained(settings.model)
        self.predictor = module.KronosPredictor(
            model, tokenizer, device=settings.device, max_context=512
        )

    def forecast(self, symbol: str, bars: list[Bar], events: list[Signal]) -> ForecastResult:
        import pandas as pd
        import torch

        count = min(self.settings.lookback, len(bars))
        history = bars[-count:]
        cache_path = self._cache_path(symbol, history)
        cached = self._read_cache(cache_path)
        if cached is not None:
            cached.cache_hit = True
            self._apply_interpretation(cached, events, history[-1].date)
            return cached
        frame = pd.DataFrame({
            "open": [bar.open for bar in history],
            "high": [bar.high for bar in history],
            "low": [bar.low for bar in history],
            "close": [bar.close for bar in history],
            "volume": [bar.volume for bar in history],
        })
        x_timestamp = pd.Series(pd.to_datetime([bar.date for bar in history]))
        # Exchange holidays are not inferred by Kronos. Weekdays are suitable timestamps;
        # the generated bars are scenarios rather than executable trading-calendar data.
        y_timestamp = pd.Series(pd.bdate_range(history[-1].date, periods=self.settings.prediction_days + 1)[1:])
        paths = []
        for path_index in range(self.settings.path_count):
            seed = self.settings.seed + path_index
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            paths.append(self.predictor.predict(
                frame, x_timestamp, y_timestamp, self.settings.prediction_days,
                T=self.settings.temperature, top_p=self.settings.top_p,
                sample_count=1, verbose=False,
            ))

        def percentile(values: list[float], ratio: float) -> float:
            ordered = sorted(values)
            index = (len(ordered) - 1) * ratio
            lower = int(index)
            upper = min(lower + 1, len(ordered) - 1)
            return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

        points = []
        for index, timestamp in enumerate(y_timestamp):
            closes = [float(path.iloc[index]["close"]) for path in paths]
            points.append(ForecastPoint(
                timestamp.date(),
                statistics.median(float(path.iloc[index]["open"]) for path in paths),
                statistics.median(float(path.iloc[index]["high"]) for path in paths),
                statistics.median(float(path.iloc[index]["low"]) for path in paths),
                statistics.median(closes), percentile(closes, .1), percentile(closes, .9),
            ))
        last_close = history[-1].close
        end_closes = [float(path.iloc[-1]["close"]) for path in paths]
        returns = [(value / last_close - 1) * 100 for value in end_closes]
        positive_ratio = sum(value > 0 for value in returns) / len(returns)
        result = ForecastResult(
            self.settings.model, count, len(paths), points, statistics.median(returns),
            percentile(returns, .1), percentile(returns, .9),
            positive_ratio, "中性", "", self.settings.seed, False,
        )
        self._apply_interpretation(result, events, history[-1].date)
        self._write_cache(cache_path, result)
        return result

    @staticmethod
    def _apply_interpretation(result: ForecastResult, events: list[Signal], as_of: date) -> None:
        recent = [event for event in events if (as_of - event.date).days <= 7]
        score = sum(1 if event.direction == "bullish" else -1 if event.direction == "bearish" else 0
                    for event in recent)
        result.abu_bias = "偏多" if score > 0 else "偏空" if score < 0 else "中性"
        model_bias = "偏多" if result.positive_path_ratio >= .65 else \
            "偏空" if result.positive_path_ratio <= .35 else "不确定"
        result.combined_view = f"近期事件计数{result.abu_bias}；Kronos 五日路径{model_bias}"
        if result.abu_bias != "中性" and model_bias != "不确定":
            result.combined_view += "，方向一致" if result.abu_bias == model_bias else "，方向分歧"

    def _cache_path(self, symbol: str, history: list[Bar]) -> Path:
        payload = {
            "symbol": symbol, "model": self.settings.model, "tokenizer": self.settings.tokenizer,
            "lookback": self.settings.lookback, "prediction_days": self.settings.prediction_days,
            "path_count": self.settings.path_count, "temperature": self.settings.temperature,
            "top_p": self.settings.top_p, "seed": self.settings.seed,
            "bars": [[bar.date.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume] for bar in history],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
        return self.cache_dir / f"{symbol}-{history[-1].date}-{digest}.json"

    @staticmethod
    def _read_cache(path: Path) -> ForecastResult | None:
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["points"] = [ForecastPoint(date.fromisoformat(item.pop("date")), **item) for item in raw["points"]]
            return ForecastResult(**raw)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    @staticmethod
    def _write_cache(path: Path, result: ForecastResult) -> None:
        from dataclasses import asdict
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = asdict(result)
        for point in raw["points"]:
            point["date"] = point["date"].isoformat()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
