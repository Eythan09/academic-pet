"""Генерирует пару VAPID-ключей для Web Push и кладёт их в secrets-to-copy.txt (файл в .gitignore).

Запуск из корня проекта: python scripts/gen_vapid.py
Ключи не печатаются в консоль. Скопируй их из файла в GitHub Secrets, потом удали файл.
"""
import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

OUT = Path(__file__).resolve().parent.parent / "secrets-to-copy.txt"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def main() -> None:
    if OUT.exists() and "--force" not in sys.argv:
        print(f"{OUT.name} уже есть. Чтобы перезаписать: python scripts/gen_vapid.py --force")
        return
    key = ec.generate_private_key(ec.SECP256R1())
    private = b64url(key.private_numbers().private_value.to_bytes(32, "big"))
    public = b64url(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))
    OUT.write_text(
        "Добавь на GitHub: Settings → Secrets and variables → Actions → New repository secret.\n"
        "После этого удали этот файл. Он в .gitignore и в репозиторий не попадёт.\n\n"
        f"VAPID_PUBLIC_KEY\n{public}\n\n"
        f"VAPID_PRIVATE_KEY\n{private}\n\n"
        "ACADEMO_USERNAME\n<твой логин от Академо>\n\n"
        "ACADEMO_PASSWORD\n<твой пароль от Академо>\n\n"
        "PUSH_SUBSCRIPTIONS\n<скопируй из приложения: ⚙ → Включить уведомления>\n",
        encoding="utf-8",
    )
    print(f"✅ Ключи записаны в {OUT.name}")


if __name__ == "__main__":
    main()
