# Bot Dashboard Guide

The bot dashboard gives you a local webpage for common bot controls.

It does not replace the bot. Start the bot first, then start the dashboard.

## 1. Start The Bot

In PowerShell:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
$env:BITRUE_BOT_CONFIG = "config/bitrue_bot.local.json"
python -m uvicorn bitrue_bot.main:app --host 127.0.0.1 --port 8000
```

Leave that window open.

## 2. Start The Dashboard

Open a second PowerShell window:

```powershell
cd C:\Users\rodst\Desktop\market_bias_dashboard
$env:BITRUE_WEBHOOK_SECRET = "my-local-test-secret-please-change-me"
streamlit run bot_dashboard.py
```

Streamlit should open a browser window automatically.

## What You Can Do

- Check bot health
- Confirm `dry_run` mode
- Turn kill switch on or off
- Disable specific symbols
- Reconcile positions
- View current positions
- Send local test alerts
- View recent bot events

## Safety Reminder

This dashboard is for local testing and supervision.

Do not expose it publicly.
