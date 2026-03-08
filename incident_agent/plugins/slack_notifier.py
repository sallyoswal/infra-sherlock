"""Slack notifier plugin using incoming webhooks."""

from __future__ import annotations

import json
import os
from typing import Callable
from urllib import error, request


def _default_sender(webhook_url: str, body: bytes) -> tuple[bool, str]:
    req = request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=5) as resp:
            code = getattr(resp, "status", 200)
        if 200 <= code < 300:
            return True, f"sent ({code})"
        return False, f"unexpected status ({code})"
    except error.URLError as exc:
        return False, str(exc)


class SlackNotifierPlugin:
    """Send incident notifications to Slack via webhook."""

    name = "slack"

    def __init__(self, sender: Callable[[str, bytes], tuple[bool, str]] | None = None) -> None:
        self._sender = sender or _default_sender

    def healthcheck(self) -> tuple[bool, str]:
        webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        if not webhook:
            return False, "SLACK_WEBHOOK_URL is missing"
        return True, "Slack webhook configured"

    def notify(self, payload: dict[str, object]) -> tuple[bool, str]:
        ok, detail = self.healthcheck()
        if not ok:
            return False, detail

        webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        message = {
            "text": str(payload.get("text", "Infra Sherlock incident update")),
            "blocks": payload.get("blocks", []),
        }
        return self._sender(webhook, json.dumps(message).encode("utf-8"))
