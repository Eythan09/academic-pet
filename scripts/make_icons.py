"""Рисует PNG-иконки Erudax (чёрный квадрат, пиксельная «E» акцентом) без сторонних библиотек.
Запуск из корня проекта: python scripts/make_icons.py
"""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "pwa"
BG = (0, 0, 0)
ACCENT = (0xFF, 0x4A, 0x1C)
# «E» на сетке 16×16 — та же, что в icon.svg; укладывается в безопасную зону maskable
E = {(x, y) for x in range(5, 11) for y in (3, 4)} | {(x, y) for x in range(5, 7) for y in range(3, 13)} \
    | {(x, y) for x in range(7, 10) for y in (7, 8)} | {(x, y) for x in range(7, 11) for y in (11, 12)}


def make(size: int, path: Path) -> None:
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            cell = (px * 16 // size, py * 16 // size)
            row += bytes(ACCENT if cell in E else BG)
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
    path.write_bytes(png)


make(192, OUT / "icon-192.png")
make(512, OUT / "icon-512.png")
print("ok")
