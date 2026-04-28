# Bot Startup Checklist

Use this checklist to start the Bitrue bot in the local safe test setup.

## Start The Bot

1. Open PowerShell

2. Go to the project folder:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
```

3. Set the webhook secret for this PowerShell window:

```powershell
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
```

4. Point the bot at the safe local config:

```powershell
$env:BITRUE_BOT_CONFIG = "config/bitrue_bot.local.json"
```

5. Start the bot:

```powershell
python -m uvicorn bitrue_bot.main:app --host 127.0.0.1 --port 8000
```

6. Leave that PowerShell window open.

That window is the running bot. If you close it, the bot stops.

## Verify The Bot

Open a second PowerShell window and run:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
$env:BITRUE_BOT_CONFIG = "config/bitrue_bot.local.json"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

You want to see:

- `ok`
- `dry_run`

## Turn Off Kill Switch

Run this in the second PowerShell window:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/control" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"kill_switch": false, "notes": "normal startup"}'
```

## Rebuild Positions

If needed:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/reconcile" -Method Post
```

## Stop The Bot

Go back to the first PowerShell window and press:

```powershell
Ctrl + C
```

## Mini Version

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
$env:BITRUE_BOT_CONFIG = "config/bitrue_bot.local.json"
python -m uvicorn bitrue_bot.main:app --host 127.0.0.1 --port 8000
```

Then in a second window:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

## Important

If `/health` shows `dry_run`, you are still in the safer test mode.

## Send A Test Alert

In a second PowerShell window:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
python scripts\send_test_alert.py --symbol BTCUSDT --signal DREAM --price 55000 --timeframe 1D
```

Examples:

```powershell
python scripts\send_test_alert.py --symbol XRPUSDT --signal S --price 2.10 --timeframe 1D
python scripts\send_test_alert.py --symbol SHIBUSDT --signal SSB30 --price 0.000013 --timeframe 3D
```

## Start The Dashboard

Start the bot first. Then open a second PowerShell window:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
streamlit run bot_dashboard.py
```

## Read-Only Mode

Read [READ_ONLY_SETUP.md](C:\Users\rodst\Desktop\market_bias_dashboard\READ_ONLY_SETUP.md) before using real Bitrue keys.

Do not paste API keys into chat.
