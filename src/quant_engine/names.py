from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path


class SymbolNameResolver:
    """Resolve mainland security names and retain a durable local cache."""

    endpoint = "https://searchapi.eastmoney.com/api/suggest/get"
    token = "D43BF722C8E33BDC906FB84D85E326E8"

    def __init__(self, cache_path: str | Path):
        self.cache_path = Path(cache_path)
        self.names = self._read()

    def resolve(self, symbol: str) -> str:
        if symbol in self.names:
            return self.names[symbol]
        code = symbol.lower().removeprefix("sh").removeprefix("sz")
        params = urllib.parse.urlencode({"input": code, "type": 14, "token": self.token})
        request = urllib.request.Request(f"{self.endpoint}?{params}", headers={"User-Agent": "Mozilla/5.0 daily-signal/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.load(response)
            candidates = payload.get("QuotationCodeTable", {}).get("Data") or []
            match = next((item for item in candidates if item.get("Code") == code), None)
            name = str(match.get("Name")).strip() if match and match.get("Name") else symbol
        except Exception:
            name = symbol
        if name != symbol:
            self.names[symbol] = name
            self._write()
        return name

    def _read(self) -> dict[str, str]:
        if not self.cache_path.exists():
            return {}
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return {str(key): str(name) for key, name in value.items()} if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.names, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.cache_path)
