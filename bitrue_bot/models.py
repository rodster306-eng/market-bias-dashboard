from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


class BotMode(str, Enum):
    DRY_RUN = "dry_run"
    READ_ONLY = "read_only"
    LIVE = "live"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(slots=True)
class SignalEvent:
    symbol: str
    action: str
    signal: str
    price: Decimal | None = None
    timeframe: str | None = None
    strategy: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = field(default_factory=dict)

    def normalized_symbol(self) -> str:
        return self.symbol.replace("/", "").replace("-", "").upper()

    def normalized_action(self) -> str:
        return self.action.strip().lower()


@dataclass(slots=True)
class SymbolConfig:
    symbol: str
    enabled: bool = True
    quote_order_qty: Decimal = Decimal("50")
    cooldown_seconds: int = 900
    allow_buy: bool = True
    allow_sell: bool = True

    def normalized_symbol(self) -> str:
        return self.symbol.replace("/", "").replace("-", "").upper()


@dataclass(slots=True)
class BotSettings:
    mode: BotMode = BotMode.DRY_RUN
    quote_asset: str = "USDT"
    recv_window: int = 5000
    max_open_positions: int = 10
    state_path: str = "data/bot_state.json"
    log_path: str = "data/bot_events.jsonl"
    runtime_control_path: str = "data/runtime_control.json"
    listen_host: str = "127.0.0.1"
    listen_port: int = 8000


@dataclass(slots=True)
class PositionState:
    symbol: str
    base_asset: str
    qty: Decimal = Decimal("0")
    last_buy_at: datetime | None = None
    last_sell_at: datetime | None = None
    last_signal_at: datetime | None = None
    last_buy_price: Decimal | None = None
    buy_history: list[dict[str, str | None]] = field(default_factory=list)

    def is_open(self) -> bool:
        return self.qty > Decimal("0")


@dataclass(slots=True)
class OrderDecision:
    allowed: bool
    reason: str
    side: OrderSide | None = None
    symbol: str | None = None
    quote_order_qty: Decimal | None = None
    quantity: Decimal | None = None
    signal: SignalEvent | None = None
    is_rebuy: bool = False


@dataclass(slots=True)
class OrderResult:
    status: str
    mode: str
    symbol: str
    side: str
    quantity: str | None = None
    quote_order_qty: str | None = None
    exchange_response: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SymbolRules:
    symbol: str
    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    step_size: Decimal | None = None
    min_notional: Decimal | None = None
    tick_size: Decimal | None = None
    price_scale: int | None = None
    volume_scale: int | None = None
