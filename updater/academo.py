"""Получение дедлайнов из Академо через тот же API, которым пользуется сайт.

Академо — Vue-приложение: HTML страницы пустой, а блок «Дедлайны» на главной
заполняется запросами:
  1. POST {API}/usercontrol/api/login  {"username", "password"}  → токен + cookie
  2. GET  {API}/study/api/academic-calendar/get-upcoming-calendar-deadline?page=N&per_page=10
     → {"data": [{type, task_id|quiz_id, task_name|quiz_name, course_id, course_name, end_date}], "last_page"}
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime, tzinfo

import httpx

log = logging.getLogger(__name__)

LOGIN_PATH = "usercontrol/api/login"
DEADLINES_PATH = "study/api/academic-calendar/get-upcoming-calendar-deadline"
MAX_PAGES = 10


class AcademoError(Exception):
    pass


@dataclass
class Deadline:
    id: str        # стабильный id из Академо, например task-123
    title: str
    course: str
    due: datetime
    url: str


def base_url() -> str:
    return os.getenv("ACADEMO_BASE_URL", "https://uib.academo.kz").rstrip("/")


def api_url() -> str:
    return os.getenv("ACADEMO_API_URL", "https://uib-api.academo.kz").rstrip("/") + "/"


def _parse_end_date(value: str, tz: tzinfo) -> datetime | None:
    """Академо отдаёт «2026-11-08 23:59:00» (местное время) или ISO-строку."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)


def _link(item: dict) -> str:
    base, course = base_url(), item.get("course_id")
    if item.get("type") == "task" and item.get("task_id"):
        return f"{base}/study/course/{course}/answer-task/{item['task_id']}"
    if item.get("type") == "quiz" and item.get("quiz_id"):
        return f"{base}/study/course/{course}/test-info/{item['quiz_id']}"
    return f"{base}/study/course/{course}" if course else base


def parse_items(items: list[dict], tz: tzinfo) -> list[Deadline]:
    """Превращает ответ API в список дедлайнов (то, что показывает блок «Дедлайны»)."""
    result, seen = [], set()
    for it in items or []:
        title = (it.get("task_name") or it.get("quiz_name") or it.get("name") or "").strip()
        due = _parse_end_date(it.get("end_date") or "", tz)
        ident = it.get("task_id") or it.get("quiz_id")
        if not title or not due or not ident:
            log.warning("Пропускаю непонятную запись (type=%s)", it.get("type"))
            continue
        did = f"{it.get('type') or 'item'}-{ident}"
        if did in seen:
            continue
        seen.add(did)
        result.append(Deadline(did, title, (it.get("course_name") or "").strip(), due, _link(it)))
    return result


def _login(client: httpx.Client, username: str, password: str) -> None:
    if not (username and password):
        raise AcademoError("Не заданы ACADEMO_USERNAME и ACADEMO_PASSWORD")
    try:
        r = client.post(LOGIN_PATH, json={"username": username, "password": password})
    except httpx.HTTPError as e:
        raise AcademoError(f"Академо недоступен: {e.__class__.__name__}") from e
    try:
        data = r.json()
    except ValueError:
        raise AcademoError(f"Академо ответил не JSON при входе (HTTP {r.status_code})")
    if r.status_code >= 400 or not data.get("success"):
        msg = data.get("message") or data.get("detail") or f"HTTP {r.status_code}"
        raise AcademoError(f"Вход не удался — проверь логин и пароль ({msg})")
    token = (data.get("token") or {}).get("access_token") or data.get("access_token") or ""
    if token:
        # Сайт хранит токен в cookie ACCESS_TOKEN и шлёт запросы с cookie
        client.cookies.set("ACCESS_TOKEN", token)
        client.headers["Authorization"] = f"Bearer {token}"


def fetch_raw(username: str, password: str) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "Accept-Language": "ru",
        "Origin": base_url(),
        "Referer": base_url() + "/",
        "User-Agent": "Mozilla/5.0 (AcademicPet)",
    }
    with httpx.Client(base_url=api_url(), headers=headers, timeout=30) as client:
        _login(client, username, password)
        items, page = [], 1
        while page <= MAX_PAGES:
            try:
                r = client.get(DEADLINES_PATH, params={"page": page, "per_page": 10})
            except httpx.HTTPError as e:
                raise AcademoError(f"Не удалось получить дедлайны: {e.__class__.__name__}") from e
            if r.status_code in (401, 403):
                raise AcademoError(f"Академо не пустил к дедлайнам (HTTP {r.status_code})")
            r.raise_for_status()
            body = r.json()
            if isinstance(body, list):
                return body
            items.extend(body.get("data") or [])
            if page >= int(body.get("last_page") or 1):
                break
            page += 1
        return items


def fetch_deadlines(username: str, password: str, tz: tzinfo) -> list[Deadline]:
    return parse_items(fetch_raw(username, password), tz)
