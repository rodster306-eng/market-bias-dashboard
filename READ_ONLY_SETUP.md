# Read-Only Bitrue Setup

Use read-only mode before any live trading.

Read-only mode lets the bot connect to Bitrue and reconcile real balances/trades, but it blocks order placement.

## Important Safety Rules

- Do not paste API keys into chat.
- Create API keys in Bitrue with withdrawal permission disabled.
- If Bitrue supports read-only keys, use read-only permission for this phase.
- Keep the bot local-only while testing.
- Keep `mode` as `read_only`, not `live`.

## Start In Read-Only Mode

In PowerShell:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
$env:BITRUE_BOT_CONFIG = "config/bitrue_bot.read_only.json"
$env:BITRUE_API_KEY = "your_api_key_here"
$env:BITRUE_API_SECRET = "your_api_secret_here"
python -m uvicorn bitrue_bot.main:app --host 127.0.0.1 --port 8000
```

Leave that window open.

## Verify Health

In a second PowerShell window:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

Expected mode:

```text
read_only
```

## Reconcile Real Account State

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/reconcile" -Method Post
```

Then inspect:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/positions"
```

## Verify Exchange Rules

Refresh the local exchange-info cache from Bitrue:

```powershell
python scripts\refresh_exchange_info.py --config config\bitrue_bot.read_only.json
```

## What Happens If An Alert Tries To Trade?

The bot can still evaluate signals, but order placement is blocked in read-only mode.

The response should show:

```json
{
  "status": "blocked",
  "mode": "read_only"
}
```

## Do Not Switch To Live Yet

Before live mode, still needed:

- tiny-size live config
- explicit live opt-in
- secure TradingView delivery path
- final confirmation that API key permissions are safe
- small manual test plan

