from __future__ import annotations

import os
from typing import Any

import requests


class NotificationManager:
    def __init__(self) -> None:
        self.webhook_url = os.getenv("BITRUE_NOTIFY_WEBHOOK_URL")

    def notify(self, title: str, details: dict[str, Any]) -> None:
        if not self.webhook_url:
            return

        lines = [f"{key}: {value}" for key, value in details.items()]
        message = {"text": f"{title}\n" + "\n".join(lines)}
        response = requests.post(self.webhook_url, json=message, timeout=10)
        response.raise_for_status()

