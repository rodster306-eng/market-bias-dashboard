from __future__ import annotations

import ipaddress
import time
from collections import deque
from dataclasses import dataclass

from .config import RuntimeConfig


@dataclass(slots=True)
class SecurityCheckResult:
    allowed: bool
    reason: str


class SecurityManager:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.allowed_networks = [ipaddress.ip_network(item, strict=False) for item in config.allowed_webhook_ips]
        self.request_times: dict[str, deque[float]] = {}
        self._validate_live_mode_configuration()

    def authorize_webhook(self, remote_host: str | None, supplied_secret: str | None) -> SecurityCheckResult:
        host = remote_host or "unknown"

        if not self._check_rate_limit(host):
            return SecurityCheckResult(allowed=False, reason="Request rate limit exceeded.")

        if self.allowed_networks and not self._is_host_allowed(host):
            return SecurityCheckResult(allowed=False, reason=f"Remote host {host} is not allowlisted.")

        expected_secret = self.config.webhook_secret
        if expected_secret:
            if not supplied_secret or supplied_secret != expected_secret:
                return SecurityCheckResult(allowed=False, reason="Webhook secret is missing or invalid.")

        return SecurityCheckResult(allowed=True, reason="Authorized.")

    def _check_rate_limit(self, host: str) -> bool:
        limit = self.config.request_limit_per_minute
        now = time.time()
        bucket = self.request_times.setdefault(host, deque())
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def _is_host_allowed(self, host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(ip in network for network in self.allowed_networks)

    def _validate_live_mode_configuration(self) -> None:
        if self.config.settings.mode.value == "read_only":
            if not self.config.api_key or not self.config.api_secret:
                raise RuntimeError("Read-only mode requires Bitrue API credentials.")
            return

        if self.config.settings.mode.value != "live":
            return
        if not self.config.allow_live_trading:
            raise RuntimeError(
                "Live mode requires BITRUE_ALLOW_LIVE_TRADING=yes_i_understand."
            )
        if not self.config.api_key or not self.config.api_secret:
            raise RuntimeError("Live mode requires Bitrue API credentials.")
        if not self.config.webhook_secret:
            raise RuntimeError("Live mode requires BITRUE_WEBHOOK_SECRET.")
        if not self.allowed_networks:
            raise RuntimeError("Live mode requires BITRUE_ALLOWED_WEBHOOK_IPS.")
