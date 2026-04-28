from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .config import RuntimeConfig
from .models import OrderDecision, OrderSide, PositionState, SignalEvent
from .runtime_control import RuntimeControl


BUY_SIGNALS = {"SB", "SSB30", "DREAM"}
SELL_SIGNALS = {"S", "H-S", "SS", "SS80"}
ALLOWED_SIGNALS = {"SSB30", "DREAM", "S", "H-S"}
TIMEFRAME_SECONDS = {"1D": 86400, "3D": 259200}


def infer_order_side(signal: SignalEvent) -> OrderSide:
    action = signal.normalized_action()
    tag = signal.signal.strip().upper()

    if action == "buy" or tag in BUY_SIGNALS:
        return OrderSide.BUY
    if action == "sell" or tag in SELL_SIGNALS:
        return OrderSide.SELL
    raise ValueError(f"Unsupported action/signal combination: action={signal.action!r}, signal={signal.signal!r}")


class RiskManager:
    def __init__(self, config: RuntimeConfig, runtime_control: RuntimeControl) -> None:
        self.config = config
        self.runtime_control = runtime_control

    def evaluate(
        self,
        signal: SignalEvent,
        positions: dict[str, PositionState],
        available_quote_balance: Decimal | None = None,
    ) -> OrderDecision:
        symbol = signal.normalized_symbol()
        normalized_signal = signal.signal.strip().upper()
        normalized_timeframe = signal.timeframe.strip().upper() if signal.timeframe else None
        if self.runtime_control.is_kill_switch_active():
            return OrderDecision(allowed=False, reason="Global kill switch is active.")
        if self.runtime_control.is_symbol_disabled(symbol):
            return OrderDecision(allowed=False, reason=f"Symbol {symbol} is disabled by runtime control.")
        if normalized_signal not in ALLOWED_SIGNALS:
            return OrderDecision(
                allowed=False,
                reason=f"Signal {normalized_signal} is not enabled. Allowed signals: SSB30, DREAM, S, H-S.",
            )
        allowed_timeframes = self.config.allowed_signal_timeframes.get(normalized_signal, set())
        if allowed_timeframes:
            if normalized_timeframe is None:
                return OrderDecision(
                    allowed=False,
                    reason=f"Signal {normalized_signal} requires timeframe metadata. Allowed timeframes: {', '.join(sorted(allowed_timeframes))}.",
                )
            if normalized_timeframe not in allowed_timeframes:
                return OrderDecision(
                    allowed=False,
                    reason=f"Signal {normalized_signal} is not allowed on timeframe {normalized_timeframe}. Allowed timeframes: {', '.join(sorted(allowed_timeframes))}.",
                )

        symbol_config = self.config.symbols.get(symbol)
        if symbol_config is None or not symbol_config.enabled:
            return OrderDecision(allowed=False, reason=f"Symbol {symbol} is not enabled.")

        side = infer_order_side(signal)
        position = positions.get(symbol)
        open_positions = sum(1 for item in positions.values() if item.is_open())

        if side == OrderSide.BUY and not symbol_config.allow_buy:
            return OrderDecision(allowed=False, reason=f"Buying is disabled for {symbol}.")
        if side == OrderSide.SELL and not symbol_config.allow_sell:
            return OrderDecision(allowed=False, reason=f"Selling is disabled for {symbol}.")

        if side == OrderSide.BUY and position and position.is_open():
            return self._evaluate_rebuy(signal, position, symbol, available_quote_balance)

        if side == OrderSide.BUY and open_positions >= self.config.settings.max_open_positions:
            return OrderDecision(allowed=False, reason="Max open positions reached.")

        if position and position.last_signal_at:
            elapsed = signal.timestamp.astimezone(timezone.utc) - position.last_signal_at.astimezone(timezone.utc)
            if elapsed.total_seconds() < symbol_config.cooldown_seconds:
                return OrderDecision(allowed=False, reason=f"Cooldown active for {symbol}.")

        if side == OrderSide.SELL:
            if not position or not position.is_open():
                return OrderDecision(allowed=False, reason=f"No open position to sell for {symbol}.")
            return OrderDecision(
                allowed=True,
                reason="Sell allowed.",
                side=side,
                symbol=symbol,
                quantity=position.qty,
                signal=signal,
            )

        return OrderDecision(
            allowed=True,
            reason="Buy allowed.",
            side=side,
            symbol=symbol,
            quote_order_qty=symbol_config.quote_order_qty,
            signal=signal,
        )

    def update_positions_from_fill(
        self,
        decision: OrderDecision,
        positions: dict[str, PositionState],
    ) -> None:
        if not decision.allowed or decision.signal is None or decision.side is None or decision.symbol is None:
            return

        symbol = decision.symbol
        base_asset = self._infer_base_asset(symbol)
        position = positions.get(symbol) or PositionState(symbol=symbol, base_asset=base_asset)
        position.last_signal_at = decision.signal.timestamp

        if decision.side == OrderSide.BUY:
            # We don't know the exact filled quantity until exchange reconciliation, so
            # the dry-run scaffold stores a placeholder open state.
            position.qty = Decimal("1")
            position.last_buy_at = decision.signal.timestamp
            position.last_buy_price = decision.signal.price
            position.buy_history.append(
                {
                    "timestamp": decision.signal.timestamp.isoformat(),
                    "price": str(decision.signal.price) if decision.signal.price is not None else None,
                    "signal": decision.signal.signal.strip().upper(),
                    "timeframe": decision.signal.timeframe.strip().upper() if decision.signal.timeframe else None,
                }
            )
        else:
            position.qty = Decimal("0")
            position.last_sell_at = decision.signal.timestamp
            position.last_buy_price = None
            position.buy_history = []

        positions[symbol] = position

    def _infer_base_asset(self, symbol: str) -> str:
        quote_asset = self.config.settings.quote_asset.upper()
        if symbol.endswith(quote_asset):
            return symbol[: -len(quote_asset)]
        return symbol

    def _evaluate_rebuy(
        self,
        signal: SignalEvent,
        position: PositionState,
        symbol: str,
        available_quote_balance: Decimal | None,
    ) -> OrderDecision:
        normalized_timeframe = signal.timeframe.strip().upper() if signal.timeframe else None
        if signal.price is None:
            return OrderDecision(allowed=False, reason=f"Buy signal for {symbol} requires a price for re-entry checks.")
        if position.last_buy_at and signal.timestamp <= position.last_buy_at:
            return OrderDecision(allowed=False, reason=f"Fresh buy signal required for {symbol}.")
        if position.last_buy_price is None:
            return OrderDecision(allowed=False, reason=f"Missing last buy price for {symbol}; cannot evaluate re-entry.")

        required_price = position.last_buy_price * (Decimal("1") - (self.config.rebuy_drop_pct / Decimal("100")))
        if signal.price > required_price:
            return OrderDecision(
                allowed=False,
                reason=f"Re-entry for {symbol} requires price at least {self.config.rebuy_drop_pct}% below last buy ({required_price:.8f} or lower).",
            )

        if normalized_timeframe is None or normalized_timeframe not in TIMEFRAME_SECONDS:
            return OrderDecision(allowed=False, reason=f"Re-entry for {symbol} requires supported timeframe metadata.")

        window_start = signal.timestamp - timedelta(
            seconds=TIMEFRAME_SECONDS[normalized_timeframe] * self.config.rebuy_window_candles
        )
        recent_buys = 0
        for entry in position.buy_history:
            ts_text = entry.get("timestamp")
            if not ts_text:
                continue
            entry_time = datetime.fromisoformat(ts_text)
            if entry_time >= window_start:
                recent_buys += 1

        if recent_buys >= self.config.rebuy_max_buys_in_window:
            return OrderDecision(
                allowed=False,
                reason=(
                    f"Re-entry cap reached for {symbol}: max {self.config.rebuy_max_buys_in_window} buys "
                    f"within {self.config.rebuy_window_candles} candles."
                ),
            )

        if available_quote_balance is None or available_quote_balance <= Decimal("0"):
            return OrderDecision(allowed=False, reason=f"Available {self.config.settings.quote_asset} balance is required for re-entry on {symbol}.")

        rebuy_quote_order_qty = (
            available_quote_balance * self.config.rebuy_wallet_pct / Decimal("100")
        ).quantize(Decimal("0.01"))
        if rebuy_quote_order_qty <= Decimal("0"):
            return OrderDecision(
                allowed=False,
                reason=(
                    f"Re-entry size for {symbol} resolved to 0 {self.config.settings.quote_asset}. "
                    f"Check available balance and rebuy_wallet_pct."
                ),
            )

        return OrderDecision(
            allowed=True,
            reason=(
                f"Re-entry allowed for {symbol}: fresh signal, price >= {self.config.rebuy_drop_pct}% below last buy, "
                f"under {self.config.rebuy_max_buys_in_window} buys in {self.config.rebuy_window_candles} candles, "
                f"and size set to {self.config.rebuy_wallet_pct}% of available {self.config.settings.quote_asset}."
            ),
            side=OrderSide.BUY,
            symbol=symbol,
            quote_order_qty=rebuy_quote_order_qty,
            signal=signal,
            is_rebuy=True,
        )
