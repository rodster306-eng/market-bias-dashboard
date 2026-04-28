from __future__ import annotations

from dataclasses import asdict

from .config import RuntimeConfig
from .exchange import BitrueSpotClient
from .logging_utils import JsonEventLogger
from .models import SignalEvent
from .notifications import NotificationManager
from .parser import parse_tradingview_payload
from .reconcile import PositionReconciler
from .risk import RiskManager
from .runtime_control import RuntimeControl
from .security import SecurityManager
from .state import StateStore


class TradingEngine:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.logger = JsonEventLogger(config.settings.log_path)
        self.state_store = StateStore(config.settings.state_path)
        self.runtime_control = RuntimeControl(config.settings.runtime_control_path)
        self.risk = RiskManager(config, self.runtime_control)
        self.exchange = BitrueSpotClient(config)
        self.reconciler = PositionReconciler(config, self.exchange)
        self.notifications = NotificationManager()
        self.security = SecurityManager(config)

    def handle_webhook_payload(self, payload: dict) -> dict:
        signal = parse_tradingview_payload(payload)
        return self.process_signal(signal)

    def reconcile_positions(self) -> dict:
        positions = self.reconciler.reconcile()
        self.state_store.save_positions(positions)
        summary = {
            symbol: {
                "qty": str(position.qty),
                "base_asset": position.base_asset,
                "last_buy_at": position.last_buy_at.isoformat() if position.last_buy_at else None,
                "last_sell_at": position.last_sell_at.isoformat() if position.last_sell_at else None,
            }
            for symbol, position in positions.items()
        }
        self.logger.write("positions_reconciled", summary)
        return summary

    def process_signal(self, signal: SignalEvent) -> dict:
        positions = self._load_positions()
        available_quote_balance = self._load_available_quote_balance()
        decision = self.risk.evaluate(signal, positions, available_quote_balance=available_quote_balance)

        self.logger.write(
            "signal_received",
            {
                "symbol": signal.normalized_symbol(),
                "action": signal.action,
                "signal": signal.signal,
                "timestamp": signal.timestamp.isoformat(),
                "decision_allowed": decision.allowed,
                "decision_reason": decision.reason,
            },
        )

        if not decision.allowed:
            self._send_notification(
                "Signal Ignored",
                {
                    "symbol": signal.normalized_symbol(),
                    "action": signal.action,
                    "signal": signal.signal,
                    "reason": decision.reason,
                },
            )
            return {
                "status": "ignored",
                "reason": decision.reason,
                "symbol": signal.normalized_symbol(),
            }

        order_result = self.exchange.place_market_order(decision)
        positions_summary = self._post_order_reconcile(decision, positions)

        self.logger.write(
            "order_submitted",
            {
                "decision": {
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "side": decision.side.value if decision.side else None,
                    "symbol": decision.symbol,
                    "quote_order_qty": str(decision.quote_order_qty) if decision.quote_order_qty is not None else None,
                    "quantity": str(decision.quantity) if decision.quantity is not None else None,
                    "is_rebuy": decision.is_rebuy,
                },
                "result": asdict(order_result),
                "positions_after_reconcile": positions_summary,
            },
        )
        self._send_notification(
            "Order Submitted",
            {
                "mode": order_result.mode,
                "symbol": order_result.symbol,
                "side": order_result.side,
                "status": order_result.status,
            },
        )

        return {
            "status": order_result.status,
            "mode": order_result.mode,
            "symbol": order_result.symbol,
            "side": order_result.side,
            "exchange_response": order_result.exchange_response,
            "positions_after_reconcile": positions_summary,
            "is_rebuy": decision.is_rebuy,
        }

    def get_runtime_control(self) -> dict:
        return self.runtime_control.load()

    def update_runtime_control(
        self,
        *,
        kill_switch: bool | None = None,
        disabled_symbols: list[str] | None = None,
        notes: str | None = None,
    ) -> dict:
        updated = self.runtime_control.update(
            kill_switch=kill_switch,
            disabled_symbols=disabled_symbols,
            notes=notes,
        )
        self.logger.write("runtime_control_updated", updated)
        self._send_notification("Runtime Control Updated", updated)
        return updated

    def get_positions(self) -> dict:
        positions = self._load_positions()
        return {
            symbol: {
                "qty": str(position.qty),
                "base_asset": position.base_asset,
                "last_buy_at": position.last_buy_at.isoformat() if position.last_buy_at else None,
                "last_sell_at": position.last_sell_at.isoformat() if position.last_sell_at else None,
                "last_signal_at": position.last_signal_at.isoformat() if position.last_signal_at else None,
            }
            for symbol, position in positions.items()
        }

    def _load_positions(self) -> dict:
        try:
            positions = self.reconciler.reconcile()
            self.state_store.save_positions(positions)
            return positions
        except Exception:
            return self.state_store.load_positions()

    def _post_order_reconcile(self, decision, fallback_positions: dict) -> dict:
        try:
            positions = self.reconciler.reconcile()
            self.state_store.save_positions(positions)
            return self._positions_summary(positions)
        except Exception:
            self.risk.update_positions_from_fill(decision, fallback_positions)
            self.state_store.save_positions(fallback_positions)
            return self._positions_summary(fallback_positions)

    def _positions_summary(self, positions: dict) -> dict:
        return {
            symbol: {
                "qty": str(position.qty),
                "base_asset": position.base_asset,
                "last_buy_at": position.last_buy_at.isoformat() if position.last_buy_at else None,
                "last_sell_at": position.last_sell_at.isoformat() if position.last_sell_at else None,
                "last_signal_at": position.last_signal_at.isoformat() if position.last_signal_at else None,
                "last_buy_price": str(position.last_buy_price) if position.last_buy_price is not None else None,
            }
            for symbol, position in positions.items()
        }

    def _load_available_quote_balance(self):
        try:
            account = self.exchange.fetch_account()
        except Exception:
            return None

        quote_asset = self.config.settings.quote_asset.upper()
        for item in account.get("balances", []):
            if str(item.get("asset", "")).upper() != quote_asset:
                continue
            return self._to_decimal(item.get("free"))
        return None

    @staticmethod
    def _to_decimal(value):
        if value in (None, ""):
            return None
        from decimal import Decimal

        return Decimal(str(value))

    def _send_notification(self, title: str, payload: dict) -> None:
        try:
            self.notifications.notify(title, payload)
        except Exception as exc:
            self.logger.write(
                "notification_error",
                {
                    "title": title,
                    "payload": payload,
                    "error": str(exc),
                },
            )
