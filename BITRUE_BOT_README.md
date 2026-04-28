# Bitrue Spot Bot Scaffold

This scaffold adds a separate Bitrue spot trading bot alongside the existing dashboard app.

## What It Does

- Accepts TradingView webhook payloads
- Parses multi-asset buy/sell signals
- Applies simple guardrails before execution
- Writes JSONL audit logs
- Persists lightweight position state locally
- Defaults to `dry_run` mode

## Project Layout

- `bitrue_bot/main.py`: FastAPI webhook entrypoint
- `bitrue_bot/engine.py`: signal-to-order orchestration
- `bitrue_bot/risk.py`: multi-asset gatekeeping and cooldowns
- `bitrue_bot/exchange.py`: Bitrue spot API client
- `bitrue_bot/state.py`: simple local position store
- `scripts/send_test_alert.py`: one-command local alert tester
- `scripts/refresh_exchange_info.py`: refresh local symbol rules from Bitrue
- `config/bitrue_bot.example.json`: starter config
- `config/bitrue_exchange_info.sample.json`: starter symbol-rule cache for dry-run testing
- `config/bitrue_account.sample.json`: starter account snapshot cache
- `config/trades_cache/*.json`: starter per-symbol trade caches
- `.env.bitrue.example`: environment variable example
- `samples/*.json`: starter TradingView webhook payloads

## Example TradingView Payload

```json
{
  "symbol": "BTCUSDT",
  "action": "buy",
  "signal": "SB",
  "secret": "replace_with_long_random_secret",
  "price": "64321.15",
  "timeframe": "4h",
  "strategy": "MRL Slim",
  "timestamp": "2026-04-18T16:00:00Z"
}
```

## Run Locally

1. Install dependencies from `requirements-bot.txt`
2. Set `BITRUE_WEBHOOK_SECRET` in your shell to a long random value
3. Start the bot with the local-only launcher:

```powershell
.\scripts\start_bitrue_bot_local.ps1
```

4. Check health:

```bash
curl http://127.0.0.1:8000/health
```

5. Send a sample webhook:

```bash
curl -X POST http://127.0.0.1:8000/webhook/tradingview ^
  -H "Content-Type: application/json" ^
  --data @samples/tradingview_buy_btc.local.json
```

6. Rebuild tracked positions from the sample account/trade snapshots:

```bash
curl -X POST http://127.0.0.1:8000/reconcile
```

7. Inspect the current tracked positions:

```bash
curl http://127.0.0.1:8000/positions
```

8. Inspect runtime control:

```bash
curl http://127.0.0.1:8000/control
```

9. Activate the kill switch:

```bash
curl -X POST http://127.0.0.1:8000/control ^
  -H "Content-Type: application/json" ^
  -d "{\"kill_switch\": true, \"notes\": \"Pause all trading\"}"
```

## Safety Notes

- The safest and easiest path is to run the bot locally on `127.0.0.1` only, in `dry_run` mode, using `config/bitrue_bot.local.json`.
- Do not expose the webhook directly to the internet while you are testing. Keep TradingView integration for a later step after local behavior is stable.
- The example config runs in `dry_run` mode by default.
- Webhook calls can require a shared secret in the payload using `secret` or `webhook_secret`.
- The bot currently accepts only `SSB30`, `DREAM`, `S`, and `H-S`.
- Timeframes are enforced: `SSB30`, `DREAM`, `S`, and `H-S` are allowed only on `1D` or `3D`.
- Re-entry buys are allowed only on a fresh `SSB30` or `DREAM` alert when price is at least 10% below the last buy, with a maximum of 3 buy executions in 8 candles.
- Re-entry size uses 20% of the available quote wallet balance instead of the fixed initial entry size.
- The example config allowlists only localhost by default; widen that only when you intentionally deploy behind a trusted network boundary.
- A basic per-IP request rate limit is enforced before webhook processing.
- The bot now validates quantity and minimum order value against Bitrue `exchangeInfo` symbol filters before sending orders.
- By default it reads a local exchange-info cache for the configured spot symbols, which keeps dry-run testing stable even without live API access.
- It can also rebuild local position state from a Bitrue account snapshot plus per-symbol trade history, using either live credentials or the sample cache files.
- A runtime control file supports a global kill switch and per-symbol disable list without editing code.
- Optional notifications can be sent to a generic webhook by setting `BITRUE_NOTIFY_WEBHOOK_URL`.
- The live BUY path converts quote sizing into base quantity using the incoming signal price, then rounds down to the exchange step size.
- Live mode refuses to start unless you explicitly opt in, provide API credentials, set a webhook secret, and define an IP allowlist.
- Read-only mode is available in `config/bitrue_bot.read_only.json` for account reconciliation without order placement.

## Recommended Path

1. Run the bot locally only with `.\scripts\start_bitrue_bot_local.ps1`
2. Use sample JSON payloads or local curl tests first
3. Keep `mode` as `dry_run`
4. Review logs in `data/bot_events.jsonl`
5. Only later decide whether you want a VPS or remote TradingView delivery path

## Send A Local Test Alert

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
python scripts\send_test_alert.py --symbol BTCUSDT --signal DREAM --price 55000 --timeframe 1D
```
