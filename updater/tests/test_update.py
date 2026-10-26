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


def test_merge_drops_task_submitted_before_due():
    fetched = parse_items(API_ITEMS, TZ)
    lst = merge([], fetched, NOW)
    # «Тест ВСК 2» (до 08.11) сдали — Академо его убрал. Срок не прошёл → это сдача, удаляем сразу
    rest = [f for f in fetched if f.id != "quiz-55"]
    assert "quiz-55" not in {d["id"] for d in merge(lst, rest, NOW + timedelta(hours=1))}


def test_notifications():
    fetched = parse_items(API_ITEMS, TZ)
    lst = merge([], fetched, NOW)
    ids = {f.id for f in fetched}

    # Первый запуск: ничего не шлём, всё запоминаем
    new, soon, urgent, over, state = plan_notifications(lst, ids, None, NOW)
    assert new == soon == urgent == over == [] and len(state["known"]) == 4

    # Через час в окно 24 часов попадает только «семинар 9» (27.10 08:00)
    new, soon, urgent, _, state = plan_notifications(lst, ids, state, NOW + timedelta(hours=1))
    assert new == [] and urgent == [] and [d["id"] for d in soon] == ["task-102"]

    # В полночь — и «СРС-1» (27.10 23:59); о семинаре повторно не напоминаем
    _, soon2, _, _, state = plan_notifications(lst, ids, state, NOW + timedelta(hours=12))
    assert [d["id"] for d in soon2] == ["task-101"]

    # Появился новый дедлайн
    extra = parse_items([{"type": "task", "task_id": 200, "task_name": "Эссе", "course_id": 9,
                          "course_name": "Философия", "end_date": "2026-11-20 23:59:00"}], TZ)
    lst2 = merge(lst, fetched + extra, NOW)
    new, soon, _, _, state = plan_notifications(lst2, ids | {"task-200"}, state, NOW + timedelta(hours=13))
    assert [d["title"] for d in new] == ["Эссе"] and soon == []

    msgs = build_messages(new, [], [], NOW)
    assert msgs[0]["title"] == "Erudax"
    assert msgs[0]["body"].startswith("Эссе через ") and "последнюю ночь" in msgs[0]["body"]


def test_urgent_repeats_until_submitted():
    fetched = parse_items(API_ITEMS, TZ)
    lst = merge([], fetched, NOW)
    ids = {f.id for f in fetched}
    *_, state = plan_notifications(lst, ids, None, NOW)
    *_, state = plan_notifications(lst, ids, state, NOW + timedelta(hours=1))  # «за 24 ч» уже было

    # «семинар 9» до 27.10 08:00. В 06:10 и в 06:40 — срочное напоминание каждый раз
    t1 = NOW + timedelta(hours=18, minutes=10)
    _, _, urgent, _, state = plan_notifications(lst, ids, state, t1)
    assert [d["id"] for d in urgent] == ["task-102"]
    _, _, urgent, _, state = plan_notifications(lst, ids, state, t1 + timedelta(minutes=30))
    assert [d["id"] for d in urgent] == ["task-102"]

    # Тексты чередуются и показывают точное время
    m1 = build_messages([], [], [], t1, urgent)[0]
    m2 = build_messages([], [], [], t1 + timedelta(minutes=30), urgent)[0]
    assert m1["body"] != m2["body"] and m1["mood"] == "panic" and m1["renotify"]
    assert "1 ч 50 мин" in m1["body"] and "1 ч 20 мин" in m2["body"]

    # В 07:10 сдал — Академо убрал задание → напоминания прекращаются, «просрочено» не будет
    gone = ids - {"task-102"}
    lst = merge(lst, [f for f in fetched if f.id != "task-102"], t1 + timedelta(minutes=60))
    _, _, urgent, _, state = plan_notifications(lst, gone, state, t1 + timedelta(minutes=60))
    assert urgent == []
    _, _, _, over, _ = plan_notifications(lst, gone, state, t1 + timedelta(hours=2, minutes=30))
    assert over == []


def test_overdue_only_if_seen_right_before_due():
    fetched = parse_items(API_ITEMS, TZ)
    lst = merge([], fetched, NOW)
    ids = {f.id for f in fetched}
    *_, state = plan_notifications(lst, ids, None, NOW)

    # 27.10 07:30 — за полчаса до срока «семинар 9» ещё в Академо
    *_, state = plan_notifications(lst, ids, state, NOW + timedelta(hours=19, minutes=30))
    assert "task-102" in state["overdue_watch"]

    # 08:07 — срок прошёл, Академо его убрал (не сдан) → одно «просрочено», и задание остаётся в списке
    later = NOW + timedelta(hours=20, minutes=7)
    rest = [f for f in fetched if f.id != "task-102"]
    lst = merge(lst, rest, later)
    assert "task-102" in {d["id"] for d in lst}
    _, _, _, over, state = plan_notifications(lst, ids - {"task-102"}, state, later)
    assert [d["id"] for d in over] == ["task-102"]
    _, _, _, over2, state = plan_notifications(lst, ids - {"task-102"}, state, later + timedelta(minutes=30))
    assert over2 == []

    # Последний раз видели в 06:30 (за 1,5 часа), потом пропало → скорее всего сдали, «просрочено» не шлём
    lst3 = merge([], fetched, NOW)
    *_, s3 = plan_notifications(lst3, ids, None, NOW)
    *_, s3 = plan_notifications(lst3, ids, s3, NOW + timedelta(hours=18, minutes=30))
    _, _, _, over3, _ = plan_notifications(lst3, ids - {"task-102"}, s3, NOW + timedelta(hours=20, minutes=7))
    assert over3 == []


def test_message_texts():
    lst = merge([], parse_items(API_ITEMS[:1], TZ), NOW)  # СРС-1, 27.10 23:59
    soon = build_messages([], lst, [], NOW + timedelta(hours=12))[0]  # 27.10 00:00 → 23 ч 59 мин
    assert soon["title"] == "Erudax"
    assert soon["body"] == "ОСТАЛОСЬ 23 Ч. Я уже грызу провода. СРС-1, СРОЧНО!!"
    assert soon["mood"] == "panic"
    over = build_messages([], [], lst, NOW + timedelta(days=2))[0]
    assert over["body"] == "СРС-1 просрочено… Я просто полежу в углу. Сдай хоть поздно, а?"
    assert over["mood"] == "sad"
    assert build_messages(lst, [], [], NOW)[0]["mood"] == "worried"


def test_fmt_left():
    from update import fmt_left
    due = (NOW + timedelta(hours=18, minutes=40)).isoformat()
    assert fmt_left(due, NOW) == "18 ч"
    assert fmt_left((NOW + timedelta(hours=50)).isoformat(), NOW) == "2 д 2 ч"
    assert fmt_left((NOW + timedelta(days=6)).isoformat(), NOW) == "6 д"
    assert fmt_left((NOW - timedelta(hours=1)).isoformat(), NOW) == "просрочено"


def test_parse_subscriptions_formats():
    sub = {"endpoint": "https://push.example/1", "keys": {"p256dh": "a", "auth": "b"}}
    sub2 = {"endpoint": "https://push.example/2", "keys": {"p256dh": "c", "auth": "d"}}
    assert parse_subscriptions(json.dumps(sub)) == [sub]
    assert parse_subscriptions(json.dumps([sub, sub2])) == [sub, sub2]
    assert parse_subscriptions(json.dumps(sub) + "\n" + json.dumps(sub2) + "\n") == [sub, sub2]
    assert parse_subscriptions("") == []
