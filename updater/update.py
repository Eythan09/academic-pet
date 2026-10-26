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
OVERDUE_WATCH_HOURS = 2
PET_NAME = "Erudax"
DEADLINES_FILE = ROOT / "pwa" / "deadlines.json"
STATE_FILE = ROOT / "data" / "state.json"


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
    """Решает, о чём уведомить. Возвращает (новые, за 24 часа, просроченные, новое состояние).
    Первый запуск (state=None) ничего не шлёт — иначе прилетели бы все дедлайны разом.

    «Просрочено» шлём один раз и только если задание ещё висело в Академо в последние
    OVERDUE_WATCH_HOURS часов до срока: если Академо убирает сданные задания, о них не напомним."""
    ids = {d["id"] for d in deadlines}
    due = {d["id"]: datetime.fromisoformat(d["due"]) for d in deadlines}
    if state is None:
        state = {"known": sorted(ids)}
        first_run = True
    else:
        first_run = False

    known = set(state.get("known", []))
    reminded = set(state.get("reminded", []))
    watch = set(state.get("overdue_watch", []))
    overdue_sent = set(state.get("overdue_sent", []))

    new = [] if first_run else [d for d in deadlines if d["id"] in fetched_ids and d["id"] not in known]
    soon = [] if first_run else [
        d for d in deadlines if d["id"] not in reminded and now < due[d["id"]] <= now + timedelta(hours=REMIND_HOURS)
    ]
    overdue = [] if first_run else [
        d for d in deadlines if d["id"] in watch and d["id"] not in overdue_sent and due[d["id"]] <= now
    ]

    known |= ids
    reminded |= {d["id"] for d in soon}
    overdue_sent |= {d["id"] for d in overdue}
    watch -= {d["id"] for d in overdue}
    watch |= {i for i in fetched_ids if i in due and now < due[i] <= now + timedelta(hours=OVERDUE_WATCH_HOURS)}

    # Не храним id удалённых дедлайнов
    new_state = {
        "known": sorted(known & ids),
        "reminded": sorted(reminded & ids),
        "overdue_watch": sorted(watch & ids),
        "overdue_sent": sorted(overdue_sent & ids),
    }
    return new, soon, overdue, new_state


def fmt_left(due_iso: str, now: datetime) -> str:
    """«18 ч», «2 д 2 ч», «6 д», «просрочено» — как в приложении."""
    h = (datetime.fromisoformat(due_iso) - now).total_seconds() / 3600
    if h < 0:
        return "просрочено"
    if h < 1:
        return "< 1 ч"
    if h < 24:
        return f"{int(h)} ч"
    d, r = int(h // 24), int(h % 24)
    return f"{d} д {r} ч" if r else f"{d} д"


def build_messages(new: list[dict], soon: list[dict], overdue: list[dict], now: datetime) -> list[dict]:
    """Тексты от лица Erudax (DESIGN.md, раздел 6)."""
    msgs = []
    if new:
        first = min(new, key=lambda d: d["due"])
        t, left = first["title"], fmt_left(first["due"], now)
        body = f"{t} через {left}. Начнёшь сегодня или опять в последнюю ночь?"
        if len(new) > 1:
            body = f"Новые дедлайны: {len(new)}. Ближайший — {body}"
        msgs.append({"title": PET_NAME, "body": body, "mood": "worried", "tag": "new-" + "-".join(d["id"] for d in new[:3])})
    for d in soon:
        left = fmt_left(d["due"], now).upper()
        msgs.append({
            "title": PET_NAME,
            "body": f"ОСТАЛОСЬ {left}. Я уже грызу провода. {d['title']}, СРОЧНО!!",
            "mood": "panic",
            "tag": "soon-" + d["id"],
        })
    for d in overdue:
        msgs.append({
            "title": PET_NAME,
            "body": f"{d['title']} просрочено… Я просто полежу в углу. Сдай хоть поздно, а?",
            "mood": "sad",
            "tag": "overdue-" + d["id"],
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
    if os.getenv("TEST_PUSH") == "true":
        sent = send_push([{"title": PET_NAME, "body": "Тест: уведомления работают! Я на связи и сторожу твои дедлайны.", "mood": "done", "tag": "test"}])
        log.info("Тестовое уведомление: доставлено на %d устройств(а)", sent)
        summary(f"🔔 Тестовое уведомление: доставлено {sent}")
    custom = os.getenv("PUSH_TEXT", "").strip()
    if custom:
        sent = send_push([{"title": PET_NAME, "body": custom[:300], "mood": "happy", "tag": "custom"}])
        log.info("Своё уведомление: доставлено на %d устройств(а)", sent)
        summary(f"💬 Своё уведомление: доставлено {sent}")
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
    new, soon, overdue, state = plan_notifications(deadlines, {f.id for f in fetched}, read_json(STATE_FILE), now)

    list_changed = deadlines != prev_list
    doc = {
        # Время последнего ИЗМЕНЕНИЯ списка (не проверки), чтобы не коммитить каждые 30 минут
        "updated_at": now.isoformat(timespec="seconds") if list_changed or not prev_doc else prev_doc.get("updated_at"),
        "keep_days": KEEP_DAYS,
        "deadlines": deadlines,
    }
    changed = write_if_changed(DEADLINES_FILE, doc)
    changed = write_if_changed(STATE_FILE, state) or changed

    messages = build_messages(new, soon, overdue, now)
    sent = 0
    if messages:
        sent = send_push(messages)

    log.info("✅ Дедлайнов в Академо: %d, в списке: %d, новых: %d, за 24 ч: %d, просрочено: %d, push доставлено: %d, файлы изменены: %s",
             len(fetched), len(deadlines), len(new), len(soon), len(overdue), sent, changed)
    summary(f"✅ Дедлайнов: {len(deadlines)} · новых: {len(new)} · за 24 ч: {len(soon)} · просрочено: {len(overdue)} · push: {sent} · изменения: {'да' if changed else 'нет'}")
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
