"""Фейковый API Академо для локальной проверки (логин test / пароль test).
Запуск: python tests/fake_academo.py  → http://127.0.0.1:8765
Повторяет два запроса, которые делает сайт: вход и список ближайших дедлайнов.
"""
import json
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "fake-token-123"


def day(n, hm="23:59:00"):
    return (datetime.now() + timedelta(days=n)).strftime(f"%Y-%m-%d {hm}")


ITEMS = [
    {"type": "task", "task_id": 1, "task_name": "СРС-1", "course_id": 7, "course_name": "История Казахстана ЛС 1688", "end_date": day(1)},
    {"type": "task", "task_id": 2, "task_name": "семинар 9", "course_id": 7, "course_name": "История Казахстана ЛС 1688", "end_date": day(1, "18:00:00")},
    {"type": "quiz", "quiz_id": 3, "quiz_name": "Тест ВСК 2", "course_id": 7, "course_name": "История Казахстана ЛС 1688", "end_date": day(13)},
    {"type": "task", "task_id": 4, "task_name": "срс-2", "course_id": 7, "course_name": "История Казахстана ЛС 1688", "end_date": day(10)},
    {"type": "quiz", "quiz_id": 5, "quiz_name": "Тест 9", "course_id": 9, "course_name": "Философия 26/27 5 semester", "end_date": day(15)},
]


class H(BaseHTTPRequestHandler):
    def _json(self, code, body, headers=None):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.rstrip("/") != "/usercontrol/api/login":
            return self._json(404, {"message": "not found"})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if body.get("username") == "test" and body.get("password") == "test":
            return self._json(200, {"success": True, "token": {"access_token": TOKEN, "expires_in": 3600},
                                    "user": {"username": "test", "roles": [{"name": "student"}]}},
                              {"Set-Cookie": "session=abc; Path=/"})
        self._json(401, {"success": False, "message": "Неверный логин или пароль"})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/study/api/academic-calendar/get-upcoming-calendar-deadline":
            return self._json(404, {"message": "not found"})
        if f"ACCESS_TOKEN={TOKEN}" not in (self.headers.get("Cookie") or ""):
            return self._json(401, {"message": "Unauthenticated"})
        q = parse_qs(url.query)
        page, per = int(q.get("page", ["1"])[0]), int(q.get("per_page", ["10"])[0])
        # Маленькие страницы, чтобы проверить пагинацию
        per = min(per, 3)
        chunk = ITEMS[(page - 1) * per: page * per]
        self._json(200, {"data": chunk, "current_page": page, "last_page": -(-len(ITEMS) // per)})


ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
