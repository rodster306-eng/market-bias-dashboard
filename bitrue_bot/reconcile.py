from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from .config import RuntimeConfig
from .exchange import BitrueSpotClient
from .models import PositionState


class PositionReconciler:
    def __init__(self, config: RuntimeConfig, exchange: BitrueSpotClient) -> None:
        self.config = config
        self.exchange = exchange

    def reconcile(self) -> dict[str, PositionState]:
        account = self.exchange.fetch_account()
        balances = {
            str(item.get("asset", "")).upper(): Decimal(str(item.get("free", "0"))) + Decimal(str(item.get("locked", "0")))
            for item in account.get("balances", [])
        }

        positions: dict[str, PositionState] = {}
        quote_asset = self.config.settings.quote_asset.upper()

        for symbol, symbol_config in self.config.symbols.items():
            if not symbol_config.enabled:
                continue

            base_asset = symbol[:-len(quote_asset)] if symbol.endswith(quote_asset) else symbol
            qty = balances.get(base_asset, Decimal("0"))
            trades = self.exchange.fetch_my_trades(symbol, limit=50)

            last_buy_at = self._latest_trade_time(trades, is_buyer=True)
            last_sell_at = self._latest_trade_time(trades, is_buyer=False)
            last_signal_at = max(
                [item for item in [last_buy_at, last_sell_at] if item is not None],
                default=None,
            )
            buy_history = self._buy_history(trades)
            last_buy_price = Decimal(str(buy_history[-1]["price"])) if buy_history else None

            positions[symbol] = PositionState(
                symbol=symbol,
                base_asset=base_asset,
                qty=qty,
                last_buy_at=last_buy_at,
                last_sell_at=last_sell_at,
                last_signal_at=last_signal_at,
                last_buy_price=last_buy_price,
                buy_history=buy_history,
            )

        return positions

    @staticmethod
    def _latest_trade_time(trades: list[dict[str, object]], is_buyer: bool) -> datetime | None:
        times: list[datetime] = []
        for trade in trades:
            if bool(trade.get("isBuyer")) != is_buyer:
                continue
            trade_time = trade.get("time")
            if trade_time is None:
                continue
            times.append(datetime.fromtimestamp(float(trade_time) / 1000.0, tz=timezone.utc))
        return max(times) if times else None

    @staticmethod
    def _buy_history(trades: list[dict[str, object]]) -> list[dict[str, str | None]]:
        latest_sell_time = None
        sell_times = [float(item.get("time", 0)) for item in trades if not bool(item.get("isBuyer")) and item.get("time") is not None]
        if sell_times:
            latest_sell_time = max(sell_times)

        history: list[dict[str, str | None]] = []
        for trade in sorted(trades, key=lambda item: float(item.get("time", 0))):
            if not bool(trade.get("isBuyer")):
                continue
            trade_time = trade.get("time")
            if trade_time is None:
                continue
            if latest_sell_time is not None and float(trade_time) <= latest_sell_time:
                continue
            history.append(
                {
                    "timestamp": datetime.fromtimestamp(float(trade_time) / 1000.0, tz=timezone.utc).isoformat(),
                    "price": str(trade.get("price", "")),
                    "signal": None,
                    "timeframe": None,
                }
            )
        return history
