import json
import urllib.parse
import urllib.request

from app.config import config

_SEVERITIES = ["INFO", "WARNING", "CRITICAL"]


class PushNotifier:
    """Config-gated external event push: Telegram bot + generic webhook.

    Each provider is a no-op when its config (token / url) is empty. Delivery is
    best-effort and never raises — alerting must never crash the pipeline.
    """

    def _enabled(self) -> bool:
        min_sev = (config.NOTIFY_MIN_SEVERITY or "WARNING").upper()
        target = (self._severity or "").upper() or "INFO"
        return _SEVERITIES.index(target) >= _SEVERITIES.index(min_sev)

    def __init__(self, severity: str = "WARNING"):
        self._severity = severity
        self._enabled_flag = self._enabled()

    def should_publish(self, severity: str) -> bool:
        if not self._enabled_flag:
            return False
        target = (severity or "INFO").upper()
        min_sev = (config.NOTIFY_MIN_SEVERITY or "WARNING").upper()
        return _SEVERITIES.index(target) >= _SEVERITIES.index(min_sev)

    def _post_form(self, url: str, payload: dict) -> None:
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=5):
            pass

    def _post_json(self, url: str, payload: dict) -> None:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass

    def notify(self, event: dict) -> None:
        if not self.should_publish(str(event.get("severity", "INFO"))):
            return

        description = event.get("description") or event.get("alert_type") or "AegisVision alert"
        prefix = f"{event.get('severity', 'INFO')} | {event.get('alert_type', 'ALERT')}"
        text = f"[AegisVision] {prefix}\n{description}"
        if event.get("camera_id"):
            text += f"\nCamera: {event['camera_id']}"
        if event.get("person_id"):
            text += f"\nPerson: {event['person_id']}"

        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            try:
                self._post_form(
                    f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                    {"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
                )
            except Exception:
                pass

        if config.NOTIFY_WEBHOOK_URL:
            try:
                self._post_json(config.NOTIFY_WEBHOOK_URL, event)
            except Exception:
                pass


def push_alert(event: dict) -> None:
    PushNotifier(severity=str(event.get("severity", "INFO"))).notify(event)