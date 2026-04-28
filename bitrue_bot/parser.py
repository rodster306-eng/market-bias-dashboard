from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import SignalEvent


def _parse_price(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)


def parse_tradingview_payload(payload: dict[str, Any]) -> SignalEvent:
    symbol = str(payload.get("symbol", "")).strip()
    action = str(payload.get("action", "")).strip()
    signal = str(payload.get("signal", "")).strip()
    if not symbol or not action or not signal:
        raise ValueError("Payload must include symbol, action, and signal.")

    return SignalEvent(
        symbol=symbol,
        action=action,
        signal=signal,
        price=_parse_price(payload.get("price")),
        timeframe=str(payload.get("timeframe", "")).strip() or None,
        strategy=str(payload.get("strategy", "")).strip() or None,
        timestamp=_parse_timestamp(payload.get("timestamp") or payload.get("time")),
        raw=payload,
    )

