from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a local TradingView-style test alert to the Bitrue bot.")
    parser.add_argument("--symbol", required=True, help="Trading pair, for example BTCUSDT.")
    parser.add_argument("--signal", required=True, choices=["SSB30", "DREAM", "S", "H-S"], help="Signal to simulate.")
    parser.add_argument("--price", required=True, help="Signal close price.")
    parser.add_argument("--timeframe", required=True, choices=["1D", "3D"], help="Alert timeframe.")
    parser.add_argument("--strategy", default="MRL Slim", help="Strategy name to include in the payload.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/webhook/tradingview", help="Local bot webhook URL.")
    return parser.parse_args()


def infer_action(signal: str) -> str:
    return "sell" if signal in {"S", "H-S"} else "buy"


def main() -> int:
    args = parse_args()
    secret = os.getenv("BITRUE_WEBHOOK_SECRET")
    if not secret:
        print("ERROR: BITRUE_WEBHOOK_SECRET is not set in this PowerShell window.")
        return 1

    payload = {
        "symbol": args.symbol.upper(),
        "action": infer_action(args.signal),
        "signal": args.signal,
        "secret": secret,
        "price": args.price,
        "timeframe": args.timeframe,
        "strategy": args.strategy,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    request = Request(
        args.url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"HTTP ERROR {exc.code}: {exc.read().decode('utf-8')}")
        return 1
    except URLError as exc:
        print(f"CONNECTION ERROR: {exc.reason}")
        print("Is the local bot running on http://127.0.0.1:8000?")
        return 1

    print("Payload:")
    print(json.dumps(payload, indent=2))
    print()
    print("Bot response:")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

