"""Проверка перед коммитом: нет ли паролей, токенов и ключей в файлах, которые попадут в git.

Запуск из корня проекта: python scripts/check_secrets.py
Значения секретов не печатаются — только файл, строка и что найдено.
"""
import fnmatch
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")


def load_gitignore() -> list[str]:
    rules = []
    gi = ROOT / ".gitignore"
    if gi.exists():
        for line in gi.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rules.append(line)
    return rules


def ignored(rel: str, rules: list[str]) -> bool:
    """Упрощённая проверка .gitignore (хватает для правил этого проекта)."""
    parts = rel.split("/")
    result = False
    for rule in rules:
        neg = rule.startswith("!")
        pat = rule[1:] if neg else rule
        pat = pat.rstrip("/")
        hit = False
        if "/" in pat:
            hit = fnmatch.fnmatch(rel, pat) or rel.startswith(pat + "/")
        else:
            hit = any(fnmatch.fnmatch(p, pat) for p in parts)
        if hit:
            result = not neg
    return result


def env_secrets() -> dict[str, str]:
    """Значения из всех .env-файлов — их не должно быть ни в одном коммитимом файле."""
    secrets = {}
    for env in ROOT.rglob(".env"):
        if ".venv" in env.parts:
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$", line)
            if not m or line.lstrip().startswith("#"):
                continue
            key, val = m.groups()
            val = val.strip("'\"")
            # Публичные адреса и настройки секретом не считаем
            if key in {"ACADEMO_BASE_URL", "ACADEMO_API_URL", "CORS_ORIGINS", "DATA_FILE", "TZ_NAME",
                       "CHECK_INTERVAL_MINUTES", "KEEP_DAYS_AFTER_DEADLINE"}:
                continue
            if len(val) >= 4:
                secrets[key] = val
    # VAPID-ключи из secrets-to-copy.txt (его создаёт scripts/gen_vapid.py)
    stc = ROOT / "secrets-to-copy.txt"
    if stc.exists():
        lines = stc.read_text(encoding="utf-8").splitlines()
        for name in ("VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY"):
            if name in lines:
                val = lines[lines.index(name) + 1].strip()
                if len(val) >= 20 and not val.startswith("<"):
                    secrets[name] = val
    return secrets


PATTERNS = {
    "Telegram-токен": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    "Приватный ключ": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub-токен": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "AWS-ключ": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Пароль в коде": re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*['\"][^'\"\s]{4,}['\"]"),
    "Заполненная переменная секрета": re.compile(
        r"(?m)^[ \t]*(ACADEMO_PASSWORD|ACADEMO_USERNAME|VAPID_PRIVATE_KEY|PUSH_SUBSCRIPTIONS)=[ \t]*[^\s#]+"),
    "Push-подписка": re.compile(r'"auth"\s*:\s*"[A-Za-z0-9_-]{16,}"'),
}
# Тестовые значения фейкового сервера — не настоящие
ALLOW = {"fake-token-123", "devtoken"}

SKIP_EXT = {".png", ".jpg", ".ico", ".pyc"}


def main() -> int:
    rules = load_gitignore()
    secrets = env_secrets()
    files, problems = [], []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or ignored(rel, rules):
            continue
        files.append(rel)
        if path.suffix in SKIP_EXT:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        for key, val in secrets.items():
            if val in text:
                problems.append(f"{rel}: содержит значение {key} из .env")
        for name, rx in PATTERNS.items():
            for m in rx.finditer(text):
                if any(a in m.group(0) for a in ALLOW):
                    continue
                if name == "Пароль в коде" and rel.startswith("backend/tests/"):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{rel}:{line}: {name}")

    # Файлы с секретами должны быть исключены
    for f in list(ROOT.rglob(".env")) + list(ROOT.glob("secrets-to-copy.txt")):
        rel = f.relative_to(ROOT).as_posix()
        if ".venv" not in f.parts and not ignored(rel, rules):
            problems.append(f"{rel}: файл с секретами НЕ исключён в .gitignore")

    print(f"Файлов попадёт в репозиторий: {len(files)}")
    for f in files:
        print("  ", f)
    print(f"\nПроверено секретов из .env: {len(secrets)} ({', '.join(sorted(secrets)) or 'нет'})")
    if problems:
        print("\n❌ Найдены проблемы:")
        for p in problems:
            print("  ", p)
        return 1
    print("\n✅ Паролей, токенов и ключей в этих файлах нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
