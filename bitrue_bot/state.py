from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .models import PositionState


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_positions(self) -> dict[str, PositionState]:
        if not self.path.exists():
            return {}

        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        positions: dict[str, PositionState] = {}
        for symbol, row in raw.get("positions", {}).items():
            positions[symbol] = PositionState(
                symbol=symbol,
                base_asset=row.get("base_asset", symbol.removesuffix("USDT")),
                qty=Decimal(str(row.get("qty", "0"))),
                last_buy_at=_parse_datetime(row.get("last_buy_at")),
                last_sell_at=_parse_datetime(row.get("last_sell_at")),
                last_signal_at=_parse_datetime(row.get("last_signal_at")),
                last_buy_price=Decimal(str(row["last_buy_price"])) if row.get("last_buy_price") not in (None, "") else None,
                buy_history=list(row.get("buy_history", [])),
            )
        return positions

    def save_positions(self, positions: dict[str, PositionState]) -> None:
        payload = {"positions": {}}
        for symbol, position in positions.items():
            row = asdict(position)
            row["qty"] = str(position.qty)
            row["last_buy_at"] = position.last_buy_at.isoformat() if position.last_buy_at else None
            row["last_sell_at"] = position.last_sell_at.isoformat() if position.last_sell_at else None
            row["last_signal_at"] = position.last_signal_at.isoformat() if position.last_signal_at else None
            row["last_buy_price"] = str(position.last_buy_price) if position.last_buy_price is not None else None
            payload["positions"][symbol] = row

        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
