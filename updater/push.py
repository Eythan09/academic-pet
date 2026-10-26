"""Отправка Web Push на устройства, где в PWA включены уведомления.

Подписки берутся из секрета PUSH_SUBSCRIPTIONS: JSON-объект подписки, массив таких
объектов или несколько объектов по одному на строку (как их копирует PWA).
"""
import json
import logging

from pywebpush import WebPushException, webpush

log = logging.getLogger(__name__)


def parse_subscriptions(raw: str) -> list[dict]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        items = []
        for line in raw.splitlines():
            line = line.strip().rstrip(",")
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("Пропускаю строку подписки: это не JSON")
    return [s for s in items if isinstance(s, dict) and s.get("endpoint") and s.get("keys")]


def send(subscriptions: list[dict], payload: dict, private_key: str, subject: str) -> int:
    """Возвращает число успешно доставленных уведомлений."""
    ok = 0
    body = json.dumps(payload, ensure_ascii=False)
    for i, sub in enumerate(subscriptions, 1):
        try:
            webpush(
                subscription_info=sub,
                data=body,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=24 * 3600,
            )
            ok += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                log.warning("Подписка №%d больше не действует (HTTP %s) — удали её из PUSH_SUBSCRIPTIONS", i, status)
            else:
                log.warning("Не удалось отправить push на подписку №%d: HTTP %s", i, status)
    return ok
