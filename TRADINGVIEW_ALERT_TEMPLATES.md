# TradingView Alert Templates

Use these webhook payload templates for the Bitrue bot.

The bot currently accepts only:

- `SSB30`
- `DREAM`
- `S`
- `H-S`

And it only accepts them on:

- `1D`
- `3D`

Replace the `secret` value with the same secret you use in your bot session.

## 1. SSB30 Buy

```json
{
  "symbol": "{{ticker}}",
  "action": "buy",
  "signal": "SSB30",
  "secret": "your-webhook-secret",
  "price": "{{close}}",
  "timeframe": "3D",
  "strategy": "MRL Slim",
  "timestamp": "{{timenow}}"
}
```

If you want the `1D` version, change:

```json
"timeframe": "1D"
```

## 2. DREAM Buy

```json
{
  "symbol": "{{ticker}}",
  "action": "buy",
  "signal": "DREAM",
  "secret": "your-webhook-secret",
  "price": "{{close}}",
  "timeframe": "3D",
  "strategy": "MRL Slim",
  "timestamp": "{{timenow}}"
}
```

If you want the `1D` version, change:

```json
"timeframe": "1D"
```

## 3. S Sell

```json
{
  "symbol": "{{ticker}}",
  "action": "sell",
  "signal": "S",
  "secret": "your-webhook-secret",
  "price": "{{close}}",
  "timeframe": "1D",
  "strategy": "MRL Slim",
  "timestamp": "{{timenow}}"
}
```

If you want the `3D` version, change:

```json
"timeframe": "3D"
```

## 4. H-S Sell

```json
{
  "symbol": "{{ticker}}",
  "action": "sell",
  "signal": "H-S",
  "secret": "your-webhook-secret",
  "price": "{{close}}",
  "timeframe": "1D",
  "strategy": "MRL Slim",
  "timestamp": "{{timenow}}"
}
```

If you want the `3D` version, change:

```json
"timeframe": "3D"
```

## Important Notes

- `{{ticker}}` should resolve to symbols like `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XLMUSDT`, `XRPUSDT`, or `SHIBUSDT`
- The bot currently trades only the symbols configured in `config/bitrue_bot.local.json`
- The `timeframe` field must match the alert timeframe you set in TradingView
- The bot will reject signals outside its allowed signal and timeframe rules
- Keep the webhook secret identical between TradingView and the bot

## Recommended Setup

- Use separate TradingView alerts for each signal and timeframe combination you want
- Keep buys on `1D` or `3D`
- Keep sells on `1D` or `3D`
- Start with only one or two alerts while testing
