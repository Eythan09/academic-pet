"""Одна проверка Академо. Запускается GitHub Actions каждые 30 минут.

1. Входит в Академо и забирает дедлайны.
2. Обновляет pwa/deadlines.json (его читает PWA) и data/state.json (о чём уже уведомляли).
   Дедлайн удаляется через KEEP_DAYS дней после срока.
3. Шлёт Web Push о новых дедлайнах и за 24 часа до срока.
Файлы перезаписываются только при реальных изменениях, поэтому коммит бывает не каждый запуск.

Локально: python updater/update.py  (логин и пароль берутся из updater/.env)
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from academo import AcademoError, Deadline, fetch_deadlines  # noqa: E402

log = logging.getLogger("updater")

TZ = ZoneInfo(os.getenv("TZ_NAME", "Asia/Almaty"))
KEEP_DAYS = 2
REMIND_HOURS = 24
DEADLINES_FILE = ROOT / "pwa" / "deadlines.json"
STATE_FILE = ROOT / "data" / "state.json"
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


# ---------- чистая логика (покрыта тестами) ----------

def expired(due_iso: str, now: datetime) -> bool:
    return now > datetime.fromisoformat(due_iso) + timedelta(days=KEEP_DAYS)


def merge(previous: list[dict], fetched: list[Deadline], now: datetime) -> list[dict]:
    """Склеивает прошлый список и свежий из Академо. Академо обычно убирает дедлайн сразу
    после срока, а мы держим его ещё KEEP_DAYS дней, потом удаляем."""
    by_id = {d["id"]: d for d in previous}
    for f in fetched:
        by_id[f.id] = {
            "id": f.id,
            "title": f.title,
            "course": f.course,
            "due": f.due.isoformat(),
            "url": f.url,
        }
    alive = [d for d in by_id.values() if not expired(d["due"], now)]
    return sorted(alive, key=lambda d: (d["due"], d["title"]))


def plan_notifications(deadlines: list[dict], fetched_ids: set[str], state: dict | None, now: datetime):
    """Решает, о чём уведомить. Возвращает (новые, напоминания, новое состояние).
    Первый запуск (state=None) ничего не шлёт — иначе прилетели бы все дедлайны разом."""
    ids = {d["id"] for d in deadlines}
    if state is None:
        return [], [], {"known": sorted(ids), "reminded": []}

    known, reminded = set(state.get("known", [])), set(state.get("reminded", []))
    new = [d for d in deadlines if d["id"] in fetched_ids and d["id"] not in known]
    soon = [
        d for d in deadlines
        if d["id"] not in reminded and now < datetime.fromisoformat(d["due"]) <= now + timedelta(hours=REMIND_HOURS)
    ]
    known |= ids
    reminded |= {d["id"] for d in soon}
    # Не храним id удалённых дедлайнов
    return new, soon, {"known": sorted(known & ids), "reminded": sorted(reminded & ids)}


def fmt_due(due_iso: str, now: datetime) -> str:
    d = datetime.fromisoformat(due_iso).astimezone(TZ)
    days = (d.date() - now.astimezone(TZ).date()).days
    day = {0: "сегодня", 1: "завтра"}.get(days, f"{d.day} {MONTHS[d.month - 1]}")
    return f"{day}, {d:%H:%M}"


def build_messages(new: list[dict], soon: list[dict], now: datetime) -> list[dict]:
    msgs = []
    if new:
        lines = [f"{d['title']} — {fmt_due(d['due'], now)}" for d in new[:5]]
        if len(new) > 5:
            lines.append(f"и ещё {len(new) - 5}")
        msgs.append({
            "title": "Новый дедлайн" if len(new) == 1 else f"Новые дедлайны: {len(new)}",
            "body": "\n".join(lines),
            "tag": "new-" + "-".join(d["id"] for d in new[:3]),
        })
    for d in soon:
        msgs.append({
            "title": f"⏰ Скоро сдавать: {d['title']}",
            "body": f"{d['course']}\nСрок: {fmt_due(d['due'], now)}",
            "tag": "soon-" + d["id"],
        })
    return msgs


# ---------- файлы ----------

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def write_if_changed(path: Path, data) -> bool:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def set_output(name: str, value: str) -> None:
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def summary(text: str) -> None:
    out = os.getenv("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(text + "\n")


# ---------- запуск ----------

def run(now: datetime | None = None) -> int:
    now = now or datetime.now(TZ)
    try:
        fetched = fetch_deadlines(os.getenv("ACADEMO_USERNAME", ""), os.getenv("ACADEMO_PASSWORD", ""), TZ)
    except AcademoError as e:
        log.error("❌ %s", e)
        summary(f"❌ Проверка Академо не удалась: {e}")
        set_output("changed", "false")
        return 1

    prev_doc = read_json(DEADLINES_FILE) or {}
    prev_list = prev_doc.get("deadlines", [])
    deadlines = merge(prev_list, fetched, now)
    new, soon, state = plan_notifications(deadlines, {f.id for f in fetched}, read_json(STATE_FILE), now)

    list_changed = deadlines != prev_list
    doc = {
        # Время последнего ИЗМЕНЕНИЯ списка (не проверки), чтобы не коммитить каждые 30 минут
        "updated_at": now.isoformat(timespec="seconds") if list_changed or not prev_doc else prev_doc.get("updated_at"),
        "keep_days": KEEP_DAYS,
        "deadlines": deadlines,
    }
    changed = write_if_changed(DEADLINES_FILE, doc)
    changed = write_if_changed(STATE_FILE, state) or changed

    messages = build_messages(new, soon, now)
    sent = 0
    if messages:
        sent = send_push(messages)

    log.info("✅ Дедлайнов в Академо: %d, в списке: %d, новых: %d, напоминаний: %d, push доставлено: %d, файлы изменены: %s",
             len(fetched), len(deadlines), len(new), len(soon), sent, changed)
    summary(f"✅ Дедлайнов: {len(deadlines)} · новых: {len(new)} · напоминаний: {len(soon)} · push: {sent} · изменения: {'да' if changed else 'нет'}")
    set_output("changed", "true" if changed else "false")
    return 0


def send_push(messages: list[dict]) -> int:
    from push import parse_subscriptions, send

    key = os.getenv("VAPID_PRIVATE_KEY", "")
    subs = parse_subscriptions(os.getenv("PUSH_SUBSCRIPTIONS", ""))
    if not key or not subs:
        log.info("Push пропущен: %s", "нет VAPID_PRIVATE_KEY" if not key else "нет подписок в PUSH_SUBSCRIPTIONS")
        return 0
    # Контакт для push-сервисов: адрес GitHub Pages (только https://домен, без пути)
    owner = os.getenv("GITHUB_REPOSITORY_OWNER", "").lower()
    subject = os.getenv("VAPID_SUBJECT") or (f"https://{owner}.github.io" if owner else "mailto:academic-pet@example.com")
    return sum(send(subs, m, key, subject) for m in messages)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass
    sys.exit(run())
