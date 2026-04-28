from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from bitrue_bot.config import load_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh local Bitrue exchange-info cache for configured symbols.")
    parser.add_argument("--config", default="config/bitrue_bot.local.json", help="Bot config path.")
    parser.add_argument("--output", default="config/bitrue_exchange_info.sample.json", help="Output cache path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_runtime_config(args.config)
    configured_symbols = set(config.symbols.keys())

    response = requests.get(f"{config.base_url}/api/v1/exchangeInfo", timeout=20)
    response.raise_for_status()
    exchange_info = response.json()

    filtered_symbols = [
        item
        for item in exchange_info.get("symbols", [])
        if str(item.get("symbol", "")).upper() in configured_symbols
    ]

    found_symbols = {str(item.get("symbol", "")).upper() for item in filtered_symbols}
    missing_symbols = sorted(configured_symbols - found_symbols)
    if missing_symbols:
        print(f"ERROR: Missing symbols from Bitrue exchangeInfo: {', '.join(missing_symbols)}")
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump({"symbols": filtered_symbols}, handle, indent=2)

    print(f"Updated {output_path} with {len(filtered_symbols)} symbols:")
    for symbol in sorted(found_symbols):
        print(f"- {symbol}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

