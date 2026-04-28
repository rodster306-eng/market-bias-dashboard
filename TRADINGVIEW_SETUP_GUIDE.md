# TradingView Setup Guide

This guide walks you through how to prepare TradingView alerts for the Bitrue bot.

Right now the bot is still running locally in `dry_run` mode, so this guide is mainly for preparing the alert setup correctly.

## Current Bot Rules

The bot currently accepts only these signals:

- `SSB30`
- `DREAM`
- `S`
- `H-S`

The bot currently accepts only these timeframes:

- `1D`
- `3D`

The bot is currently configured for only these pairs:

- `BTCUSDT`
- `ETHUSDT`
- `SOLUSDT`
- `XLMUSDT`
- `XRPUSDT`
- `SHIBUSDT`

## Before You Start

Make sure:

1. Your Pine script is showing the signals you want on the chart
2. You know which timeframe you want the alert to come from
3. You use the correct signal name in the alert payload
4. Your webhook secret matches the bot secret exactly

## Step 1. Open The Correct Chart

Open TradingView and load the chart for the pair you want, for example:

- `BTCUSDT`
- `ETHUSDT`
- `SOLUSDT`

Then set the chart timeframe to one the bot accepts:

- `1D`
- `3D`

If you create an alert from another timeframe like `4H`, the bot will reject it.

## Step 2. Load Your Pine Script

Add your Pine script to the chart and make sure it is plotting the signals you want:

- `SSB30`
- `DREAM`
- `S`
- `H-S`

## Step 3. Create The Alert

In TradingView:

1. Click the `Alert` button
2. Choose the condition based on your script signal
3. Choose the correct timeframe chart before creating the alert

You will usually want separate alerts for:

- `SSB30` on `1D`
- `SSB30` on `3D`
- `DREAM` on `1D`
- `DREAM` on `3D`
- `S` on `1D`
- `S` on `3D`
- `H-S` on `1D`
- `H-S` on `3D`

You do not need to create all of them at once. Start small.

## Step 4. Use Webhook Alerts

When you are ready to connect alerts later, you will use:

- the `Webhook URL` field in TradingView
- the JSON alert message body

For now, because the bot is local-only, TradingView cannot reach it directly.

So at this stage:

- you can prepare the alert messages
- you can save the alert setup plan
- but you should not try to send live TradingView webhooks to `127.0.0.1`

That only works from your own machine, not from TradingView’s servers.

## Step 5. Paste The Alert Message

Use the templates from:

[TRADINGVIEW_ALERT_TEMPLATES.md](C:\Users\rodst\Desktop\market_bias_dashboard\TRADINGVIEW_ALERT_TEMPLATES.md)

Pick the correct template for the signal:

- buy alerts: `SSB30`, `DREAM`
- sell alerts: `S`, `H-S`

Then make sure the `timeframe` field matches the chart timeframe.

Examples:

- if the alert is on a `1D` chart, the payload should say `"timeframe": "1D"`
- if the alert is on a `3D` chart, the payload should say `"timeframe": "3D"`

## Step 6. Keep The Secret Consistent

The `secret` field in the alert message must match your bot’s secret exactly.

Example:

```json
"secret": "my-local-test-secret-please-change-me"
```

If the secret does not match, the bot will reject the alert.

## Step 7. Use Separate Alerts

The cleanest setup is:

- one alert per signal
- one timeframe per alert
- one message template per alert

That makes it easier to debug later.

## Recommended Beginner Setup

Start with only a few alerts:

1. `SSB30` on `1D`
2. `DREAM` on `1D`
3. `S` on `1D`
4. `H-S` on `1D`

Once that feels clear, you can decide whether to also add the `3D` versions.

## Common Mistakes

- Using the wrong chart timeframe
- Sending a signal the bot does not allow
- Forgetting to match the `secret`
- Using a symbol outside `BTCUSDT`, `ETHUSDT`, `SOLUSDT`
- Using a symbol that has not been added to the bot config
- Sending alerts from `4H` or another unsupported timeframe

## Important Reminder

Right now the bot is still:

- local-only
- `dry_run`
- not directly reachable from TradingView

So this guide is for setting up the alert format correctly first.

The later step will be choosing a safe way for TradingView alerts to reach the bot.
