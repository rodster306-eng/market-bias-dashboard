from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .models import BotMode, BotSettings, SymbolConfig


@dataclass(slots=True)
class RuntimeConfig:
    settings: BotSettings
    symbols: dict[str, SymbolConfig]
    api_key: str | None
    api_secret: str | None
    base_url: str
    exchange_info_cache_path: str | None
    account_snapshot_cache_path: str | None
    trades_cache_dir: str | None
    webhook_secret: str | None
    allowed_webhook_ips: list[str]
    allow_live_trading: bool
    request_limit_per_minute: int
    allowed_signal_timeframes: dict[str, set[str]]
    rebuy_drop_pct: Decimal
    rebuy_max_buys_in_window: int
    rebuy_window_candles: int
    rebuy_wallet_pct: Decimal


def _decimal(value: object, default: str) -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def load_runtime_config(config_path: str | os.PathLike[str]) -> RuntimeConfig:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    settings_raw = raw.get("settings", {})
    settings = BotSettings(
        mode=BotMode(settings_raw.get("mode", "dry_run")),
        quote_asset=settings_raw.get("quote_asset", "USDT"),
        recv_window=int(settings_raw.get("recv_window", 5000)),
        max_open_positions=int(settings_raw.get("max_open_positions", 10)),
        state_path=settings_raw.get("state_path", "data/bot_state.json"),
        log_path=settings_raw.get("log_path", "data/bot_events.jsonl"),
        runtime_control_path=settings_raw.get("runtime_control_path", "data/runtime_control.json"),
        listen_host=settings_raw.get("listen_host", "127.0.0.1"),
        listen_port=int(settings_raw.get("listen_port", 8000)),
    )

    symbols: dict[str, SymbolConfig] = {}
    for symbol_entry in raw.get("symbols", []):
        symbol = SymbolConfig(
            symbol=symbol_entry["symbol"],
            enabled=bool(symbol_entry.get("enabled", True)),
            quote_order_qty=_decimal(symbol_entry.get("quote_order_qty"), "50"),
            cooldown_seconds=int(symbol_entry.get("cooldown_seconds", 900)),
            allow_buy=bool(symbol_entry.get("allow_buy", True)),
            allow_sell=bool(symbol_entry.get("allow_sell", True)),
        )
        symbols[symbol.normalized_symbol()] = symbol

    api_key = os.getenv("BITRUE_API_KEY")
    api_secret = os.getenv("BITRUE_API_SECRET")
    base_url = os.getenv("BITRUE_SPOT_BASE_URL", raw.get("base_url", "https://openapi.bitrue.com"))
    exchange_info_cache_path = os.getenv(
        "BITRUE_EXCHANGE_INFO_CACHE",
        raw.get("exchange_info_cache_path", "config/bitrue_exchange_info.sample.json"),
    )
    account_snapshot_cache_path = os.getenv(
        "BITRUE_ACCOUNT_SNAPSHOT_CACHE",
        raw.get("account_snapshot_cache_path", "config/bitrue_account.sample.json"),
    )
    trades_cache_dir = os.getenv(
        "BITRUE_TRADES_CACHE_DIR",
        raw.get("trades_cache_dir", "config/trades_cache"),
    )
    webhook_secret = os.getenv("BITRUE_WEBHOOK_SECRET")
    allowed_webhook_ips = [
        item.strip()
        for item in os.getenv("BITRUE_ALLOWED_WEBHOOK_IPS", raw.get("allowed_webhook_ips", "")).split(",")
        if item.strip()
    ]
    allow_live_trading = os.getenv("BITRUE_ALLOW_LIVE_TRADING", "").strip().lower() == "yes_i_understand"
    request_limit_per_minute = int(os.getenv("BITRUE_REQUEST_LIMIT_PER_MINUTE", raw.get("request_limit_per_minute", 60)))
    raw_signal_timeframes = raw.get(
        "allowed_signal_timeframes",
        {
            "SSB30": ["1D", "3D"],
            "DREAM": ["1D", "3D"],
            "S": ["1D", "3D"],
            "H-S": ["1D", "3D"],
        },
    )
    allowed_signal_timeframes = {
        str(signal).upper(): {str(item).upper() for item in values}
        for signal, values in raw_signal_timeframes.items()
    }
    rebuy_drop_pct = _decimal(raw.get("rebuy_drop_pct", 10), "10")
    rebuy_max_buys_in_window = int(raw.get("rebuy_max_buys_in_window", 3))
    rebuy_window_candles = int(raw.get("rebuy_window_candles", 8))
    rebuy_wallet_pct = _decimal(raw.get("rebuy_wallet_pct", 20), "20")

    return RuntimeConfig(
        settings=settings,
        symbols=symbols,
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
        exchange_info_cache_path=exchange_info_cache_path,
        account_snapshot_cache_path=account_snapshot_cache_path,
        trades_cache_dir=trades_cache_dir,
        webhook_secret=webhook_secret,
        allowed_webhook_ips=allowed_webhook_ips,
        allow_live_trading=allow_live_trading,
        request_limit_per_minute=request_limit_per_minute,
        allowed_signal_timeframes=allowed_signal_timeframes,
        rebuy_drop_pct=rebuy_drop_pct,
        rebuy_max_buys_in_window=rebuy_max_buys_in_window,
        rebuy_window_candles=rebuy_window_candles,
        rebuy_wallet_pct=rebuy_wallet_pct,
    )
