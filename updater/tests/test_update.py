"""Тесты разбора ответа Академо, склейки списка и решений об уведомлениях."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from academo import parse_items  # noqa: E402
from push import parse_subscriptions  # noqa: E402
from update import build_messages, merge, plan_notifications  # noqa: E402

TZ = ZoneInfo("Asia/Almaty")
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=TZ)

API_ITEMS = [
    {"type": "task", "task_id": 101, "task_name": "СРС-1", "course_id": 7, "course_name": "История Казахстана ЛС 1688", "end_date": "2026-10-27 23:59:00"},
    {"type": "task", "task_id": 102, "task_name": "семинар 9", "course_id": 7, "course_name": "История Казахстана ЛС 1688", "end_date": "2026-10-27 08:00:00"},
    {"type": "quiz", "quiz_id": 55, "quiz_name": "Тест ВСК 2", "course_id": 7, "course_name": "История Казахстана ЛС 1688", "end_date": "2026-11-08 23:59:00"},
    {"type": "quiz", "quiz_id": 56, "quiz_name": "Тест 9", "course_id": 9, "course_name": "Философия 26/27 5 semester", "end_date": "2026-11-10T23:59:00"},
    {"type": "task", "task_id": 104, "task_name": "", "end_date": "2026-11-10 23:59:00"},  # мусор
    {"type": "task", "task_id": 101, "task_name": "СРС-1", "course_id": 7, "course_name": "дубль", "end_date": "2026-10-27 23:59:00"},
]


def test_parse_items():
    items = parse_items(API_ITEMS, TZ)
    assert [i.id for i in items] == ["task-101", "task-102", "quiz-55", "quiz-56"]
    assert items[1].due.hour == 8 and items[1].due.tzinfo == TZ
    assert items[0].url.endswith("/study/course/7/answer-task/101")
    assert items[2].url.endswith("/study/course/7/test-info/55")


def test_merge_keeps_then_drops_after_two_days():
    fetched = parse_items(API_ITEMS, TZ)
    lst = merge([], fetched, NOW)
    assert len(lst) == 4
    assert lst[0]["id"] == "task-102"  # отсортировано по сроку

    # Академо убрал «семинар 9» после срока — мы держим его ещё 2 дня
    later = NOW + timedelta(days=3)  # 29.10 12:00, срок был 27.10 08:00 → +2 дня = 29.10 08:00
    rest = [f for f in fetched if f.id != "task-102"]
    assert "task-102" not in {d["id"] for d in merge(lst, rest, later)}
    assert "task-102" in {d["id"] for d in merge(lst, rest, NOW + timedelta(days=2))}

    # Повторная склейка с теми же данными ничего не меняет (значит, не будет лишнего коммита)
    assert merge(lst, fetched, NOW) == lst


def test_notifications():
    fetched = parse_items(API_ITEMS, TZ)
    lst = merge([], fetched, NOW)
    ids = {f.id for f in fetched}

    # Первый запуск: ничего не шлём, всё запоминаем
    new, soon, state = plan_notifications(lst, ids, None, NOW)
    assert new == [] and soon == [] and len(state["known"]) == 4

    # Через час в окно 24 часов попадает только «семинар 9» (27.10 08:00)
    new, soon, state = plan_notifications(lst, ids, state, NOW + timedelta(hours=1))
    assert new == [] and [d["id"] for d in soon] == ["task-102"]

    # В полночь — и «СРС-1» (27.10 23:59); о семинаре повторно не напоминаем
    _, soon2, state = plan_notifications(lst, ids, state, NOW + timedelta(hours=12))
    assert [d["id"] for d in soon2] == ["task-101"]

    # Появился новый дедлайн
    extra = parse_items([{"type": "task", "task_id": 200, "task_name": "Эссе", "course_id": 9,
                          "course_name": "Философия", "end_date": "2026-11-20 23:59:00"}], TZ)
    lst2 = merge(lst, fetched + extra, NOW)
    new, soon, state = plan_notifications(lst2, ids | {"task-200"}, state, NOW + timedelta(hours=3))
    assert [d["title"] for d in new] == ["Эссе"] and soon == []

    msgs = build_messages(new, [], NOW)
    assert msgs[0]["title"] == "Новый дедлайн" and "Эссе" in msgs[0]["body"]


def test_reminder_message_text():
    lst = merge([], parse_items(API_ITEMS[:1], TZ), NOW)
    msg = build_messages([], lst, NOW)[0]
    assert msg["title"] == "⏰ Скоро сдавать: СРС-1"
    assert "завтра, 23:59" in msg["body"]


def test_parse_subscriptions_formats():
    sub = {"endpoint": "https://push.example/1", "keys": {"p256dh": "a", "auth": "b"}}
    sub2 = {"endpoint": "https://push.example/2", "keys": {"p256dh": "c", "auth": "d"}}
    assert parse_subscriptions(json.dumps(sub)) == [sub]
    assert parse_subscriptions(json.dumps([sub, sub2])) == [sub, sub2]
    assert parse_subscriptions(json.dumps(sub) + "\n" + json.dumps(sub2) + "\n") == [sub, sub2]
    assert parse_subscriptions("") == []
