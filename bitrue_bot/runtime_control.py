from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RuntimeControl:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(
                {
                    "kill_switch": False,
                    "disabled_symbols": [],
                    "notes": "",
                }
            )

    def load(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def update(
        self,
        *,
        kill_switch: bool | None = None,
        disabled_symbols: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        current = self.load()
        if kill_switch is not None:
            current["kill_switch"] = bool(kill_switch)
        if disabled_symbols is not None:
            current["disabled_symbols"] = sorted(
                {
                    str(symbol).replace("/", "").replace("-", "").upper()
                    for symbol in disabled_symbols
                    if str(symbol).strip()
                }
            )
        if notes is not None:
            current["notes"] = notes
        self._write(current)
        return current

    def is_kill_switch_active(self) -> bool:
        return bool(self.load().get("kill_switch", False))

    def is_symbol_disabled(self, symbol: str) -> bool:
        normalized = symbol.replace("/", "").replace("-", "").upper()
        disabled = self.load().get("disabled_symbols", [])
        return normalized in {str(item).upper() for item in disabled}

    def _write(self, payload: dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

