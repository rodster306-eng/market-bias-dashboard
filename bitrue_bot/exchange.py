from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from .config import RuntimeConfig
from .models import OrderDecision, OrderResult, SymbolRules


class BitrueSpotClient:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self._symbol_rules: dict[str, SymbolRules] = {}

    def place_market_order(self, decision: OrderDecision) -> OrderResult:
        if decision.side is None or decision.symbol is None:
            raise ValueError("Decision must include side and symbol.")

        quantity_value = None
        if decision.side.value == "BUY":
            if decision.signal is None or decision.signal.price is None or decision.quote_order_qty is None:
                raise RuntimeError("BUY orders require a signal price and quote_order_qty.")
            quantity_value = self.prepare_buy_quantity(
                symbol=decision.symbol,
                quote_order_qty=decision.quote_order_qty,
                signal_price=decision.signal.price,
            )
        else:
            if decision.quantity is None:
                raise RuntimeError("SELL orders require quantity.")
            quantity_value = self.validate_sell_quantity(decision.symbol, decision.quantity)

        if self.config.settings.mode.value == "dry_run":
            return OrderResult(
                status="accepted",
                mode=self.config.settings.mode.value,
                symbol=decision.symbol,
                side=decision.side.value,
                quantity=str(quantity_value) if quantity_value is not None else None,
                quote_order_qty=str(decision.quote_order_qty) if decision.quote_order_qty is not None else None,
                exchange_response={"dry_run": True},
            )

        if self.config.settings.mode.value == "read_only":
            return OrderResult(
                status="blocked",
                mode=self.config.settings.mode.value,
                symbol=decision.symbol,
                side=decision.side.value,
                quantity=str(quantity_value) if quantity_value is not None else None,
                quote_order_qty=str(decision.quote_order_qty) if decision.quote_order_qty is not None else None,
                exchange_response={"read_only": True, "reason": "Order placement is disabled in read_only mode."},
            )

        if not self.config.api_key or not self.config.api_secret:
            raise RuntimeError("BITRUE_API_KEY and BITRUE_API_SECRET must be set for live mode.")

        params = {
            "symbol": decision.symbol,
            "side": decision.side.value,
            "type": "MARKET",
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.config.settings.recv_window,
        }
        params["quantity"] = format(quantity_value, "f")

        signed_query = self._sign(params)
        response = requests.post(
            f"{self.config.base_url}/api/v1/order",
            data=signed_query,
            headers={"X-MBX-APIKEY": self.config.api_key},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        return OrderResult(
            status="accepted",
            mode=self.config.settings.mode.value,
            symbol=decision.symbol,
            side=decision.side.value,
            quantity=params.get("quantity"),
            exchange_response=payload,
        )

    def fetch_account(self) -> dict[str, Any]:
        if self.config.api_key and self.config.api_secret:
            return self._signed_get("/api/v1/account")
        cache_path = self.config.account_snapshot_cache_path
        if cache_path and Path(cache_path).exists():
            with Path(cache_path).open("r", encoding="utf-8") as handle:
                return json.load(handle)
        raise RuntimeError("No Bitrue credentials or account snapshot cache available.")

    def fetch_exchange_info(self) -> dict[str, Any]:
        response = requests.get(f"{self.config.base_url}/api/v1/exchangeInfo", timeout=15)
        response.raise_for_status()
        return response.json()

    def fetch_my_trades(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        if self.config.api_key and self.config.api_secret:
            return self._signed_get(
                "/api/v2/myTrades",
                {"symbol": symbol.upper(), "limit": limit},
            )

        trades_cache_dir = self.config.trades_cache_dir
        if trades_cache_dir:
            path = Path(trades_cache_dir) / f"{symbol.upper()}.json"
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
        return []

    def get_symbol_rules(self, symbol: str) -> SymbolRules:
        normalized_symbol = symbol.upper()
        if normalized_symbol in self._symbol_rules:
            return self._symbol_rules[normalized_symbol]

        exchange_info = self._load_exchange_info()
        for item in exchange_info.get("symbols", []):
            item_symbol = str(item.get("symbol", "")).upper()
            rules = SymbolRules(symbol=item_symbol)
            for filter_item in item.get("filters", []):
                filter_type = filter_item.get("filterType")
                if filter_type == "LOT_SIZE":
                    rules.min_qty = self._to_decimal(filter_item.get("minQty"))
                    rules.max_qty = self._to_decimal(filter_item.get("maxQty"))
                    rules.step_size = self._to_decimal(filter_item.get("stepSize"))
                    rules.min_notional = self._to_decimal(filter_item.get("minVal"))
                    rules.volume_scale = self._to_int(filter_item.get("volumeScale"))
                elif filter_type == "PRICE_FILTER":
                    rules.tick_size = self._to_decimal(filter_item.get("tickSize"))
                    rules.price_scale = self._to_int(filter_item.get("priceScale"))
            self._symbol_rules[item_symbol] = rules

        if normalized_symbol not in self._symbol_rules:
            raise RuntimeError(f"Bitrue exchangeInfo does not include symbol {normalized_symbol}.")
        return self._symbol_rules[normalized_symbol]

    def _load_exchange_info(self) -> dict[str, Any]:
        cache_path = self.config.exchange_info_cache_path
        if cache_path:
            path = Path(cache_path)
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
        return self.fetch_exchange_info()

    def prepare_buy_quantity(self, symbol: str, quote_order_qty: Decimal, signal_price: Decimal) -> Decimal:
        if signal_price <= Decimal("0"):
            raise RuntimeError("Signal price must be positive.")
        raw_quantity = quote_order_qty / signal_price
        quantity = self._normalize_quantity(symbol, raw_quantity)
        self._validate_notional(symbol, quantity, signal_price)
        return quantity

    def validate_sell_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        normalized_quantity = self._normalize_quantity(symbol, quantity)
        return normalized_quantity

    def _normalize_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        rules = self.get_symbol_rules(symbol)
        normalized = quantity
        if rules.step_size and rules.step_size > Decimal("0"):
            normalized = (quantity / rules.step_size).to_integral_value(rounding=ROUND_DOWN) * rules.step_size
        elif rules.volume_scale is not None:
            quantum = Decimal("1").scaleb(-rules.volume_scale)
            normalized = quantity.quantize(quantum, rounding=ROUND_DOWN)

        if rules.min_qty and normalized < rules.min_qty:
            raise RuntimeError(f"Quantity {normalized} is below Bitrue minQty {rules.min_qty} for {symbol}.")
        if rules.max_qty and normalized > rules.max_qty:
            raise RuntimeError(f"Quantity {normalized} is above Bitrue maxQty {rules.max_qty} for {symbol}.")
        if normalized <= Decimal("0"):
            raise RuntimeError(f"Quantity normalized to {normalized} for {symbol}.")
        return normalized

    def _validate_notional(self, symbol: str, quantity: Decimal, signal_price: Decimal) -> None:
        rules = self.get_symbol_rules(symbol)
        if rules.min_notional is None:
            return
        notional = quantity * signal_price
        if notional < rules.min_notional:
            raise RuntimeError(
                f"Order value {notional} is below Bitrue minVal {rules.min_notional} for {symbol}."
            )

    def _signed_get(self, path: str, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.api_key or not self.config.api_secret:
            raise RuntimeError("BITRUE_API_KEY and BITRUE_API_SECRET must be set.")
        params = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.config.settings.recv_window,
        }
        if extra_params:
            params.update(extra_params)
        response = requests.get(
            f"{self.config.base_url}{path}?{self._sign(params)}",
            headers={"X-MBX-APIKEY": self.config.api_key},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={signature}"

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)
