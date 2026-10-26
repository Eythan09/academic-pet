"""Рисует иконки Erudax из того же спрайта, что и приложение (pwa/pet.js), без сторонних библиотек.

Создаёт:
  pwa/icon-192.png, pwa/icon-512.png, pwa/icon.svg — иконка приложения (спокойный волчонок)
  pwa/notify/<mood>.png                         — картинки уведомлений под настроение
  pwa/notify/badge.png                          — маленький белый силуэт для строки состояния Android

Запуск из корня проекта: python scripts/make_icons.py
"""
import json
import re
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PWA = ROOT / "pwa"
PALETTE = {"K": (0x14, 0x14, 0x14), "W": (0xF4, 0xF4, 0xF0), "G": (0x5C, 0x5C, 0x5C), "A": (0xFF, 0x4A, 0x1C)}
BG = (0, 0, 0)


# ---------- спрайт из pet.js (единственный источник) ----------

def load_form() -> dict:
    src = (PWA / "pet.js").read_text(encoding="utf-8")
    block = src[src.index('id: "pup"'):src.index("// Пример будущей эволюции")]
    grid = re.findall(r'^\s*"([.KWGAefmn]{20})",', block, re.M)
    slots = {k: json.loads(v) for k, v in re.findall(r"^\s*([efmn]):\s*(\[\[.*?\]\]),", block, re.M)}
    moods = {}
    for name, body in re.findall(r"^\s*(happy|worried|panic|sad|done):\s*\{(.*)\},", block, re.M):
        moods[name] = json.loads("{" + re.sub(r"(\b[efmnx]):", r'"\1":', body) + "}")
    assert len(grid) == 18 and len(moods) == 5 and len(slots) == 4, "не удалось разобрать pet.js"
    return {"grid": grid, "slots": slots, "moods": moods}


def cells(form: dict, mood: str) -> list[list[str]]:
    cfg = form["moods"][mood]
    out = []
    for row in form["grid"]:
        line = []
        for c, ch in enumerate(row):
            groups = form["slots"].get(ch)
            if groups:
                i = next(i for i, cols in enumerate(groups) if c in cols)
                ch = cfg[ch][i]
            line.append(ch)
        out.append(line)
    for r, c, v in cfg["x"]:
        out[r][c] = v
    return out


# ---------- PNG ----------

def write_png(path: Path, size: int, pixel_fn, alpha: bool = False) -> None:
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            row += bytes(pixel_fn(x, y))
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    color_type = 6 if alpha else 2
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, color_type, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def sprite_png(path: Path, grid, size: int, fill: float) -> None:
    """Спрайт по центру чёрного квадрата. fill — доля ширины под спрайт (0.6 для maskable-зоны)."""
    rows, cols = len(grid), len(grid[0])
    cell = max(1, int(size * fill / cols))
    ox, oy = (size - cols * cell) // 2, (size - rows * cell) // 2

    def px(x, y):
        c, r = (x - ox) // cell, (y - oy) // cell
        if 0 <= r < rows and 0 <= c < cols and x >= ox and y >= oy:
            return PALETTE.get(grid[r][c], BG)
        return BG

    write_png(path, size, px)


def badge_png(path: Path, grid, size: int) -> None:
    """Белый силуэт на прозрачном фоне: Android сам перекрашивает бейдж."""
    rows, cols = len(grid), len(grid[0])
    cell = max(1, int(size * 0.9 / cols))
    ox, oy = (size - cols * cell) // 2, (size - rows * cell) // 2

    def px(x, y):
        c, r = (x - ox) // cell, (y - oy) // cell
        inside = 0 <= r < rows and 0 <= c < cols and x >= ox and y >= oy and grid[r][c] != "."
        return (255, 255, 255, 255) if inside else (0, 0, 0, 0)

    write_png(path, size, px, alpha=True)


def sprite_svg(path: Path, grid) -> None:
    rows, cols = len(grid), len(grid[0])
    pad = 6
    w = cols + pad * 2
    hexes = {k: "#%02X%02X%02X" % v for k, v in PALETTE.items()}
    rects = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch in hexes:
                rects.append(f'<rect x="{c + pad}" y="{r + (w - rows) // 2}" width="1" height="1" fill="{hexes[ch]}"/>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {w}" shape-rendering="crispEdges">\n'
        f'<rect width="{w}" height="{w}" fill="#000"/>\n' + "\n".join(rects) + "\n</svg>\n",
        encoding="utf-8",
    )


def main() -> None:
    form = load_form()
    happy = cells(form, "happy")
    sprite_png(PWA / "icon-512.png", happy, 512, 0.6)   # 60% — помещается в круглую маску Android
    sprite_png(PWA / "icon-192.png", happy, 192, 0.6)
    sprite_svg(PWA / "icon.svg", happy)
    for mood in form["moods"]:
        sprite_png(PWA / "notify" / f"{mood}.png", cells(form, mood), 192, 0.8)
    badge_png(PWA / "notify" / "badge.png", happy, 96)
    print("ok:", ", ".join(["icon-192/512", "icon.svg"] + [f"notify/{m}" for m in form["moods"]] + ["notify/badge"]))


if __name__ == "__main__":
    main()
