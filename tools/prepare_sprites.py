"""Optimize character sprites: remove solid backgrounds, crop, and shrink every frame by one shared ratio.

usage: python tools/prepare_sprites.py <out_dir> <name>=<source.png> [<name>=<source.png> ...]
example: python tools/prepare_sprites.py assets/characters/anpanman stand=a.png walk_1=b.png walk_2=c.png fly=d.png
"""
import os
import sys
from collections import deque

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage

MAX_H = 256        # tallest frame after shrinking (enough for 2x-DPI display at 120~150 px)
BG_TOLERANCE = 10  # r+g+b distance from the corner color still counted as background


def clear_background(img):
    """Flood-fill from the borders, making pixels close to the corner color transparent."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    buf = bytearray(img.constBits().tobytes())
    stride = img.bytesPerLine()
    bb, bg, br = buf[0], buf[1], buf[2]

    def is_bg(i):
        return abs(buf[i] - bb) + abs(buf[i + 1] - bg) + abs(buf[i + 2] - br) <= BG_TOLERANCE

    seen = bytearray(w * h)
    queue = deque()
    for x in range(w):
        queue.extend(((x, 0), (x, h - 1)))
    for y in range(h):
        queue.extend(((0, y), (w - 1, y)))
    while queue:
        x, y = queue.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or seen[y * w + x]:
            continue
        seen[y * w + x] = 1
        i = y * stride + x * 4
        if not is_bg(i):
            continue
        buf[i:i + 4] = b"\0\0\0\0"
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return QImage(bytes(buf), w, h, stride, QImage.Format_ARGB32).copy()


def opaque_bounds(img):
    w, h = img.width(), img.height()
    alpha = img.convertToFormat(QImage.Format_Alpha8)
    data = alpha.constBits().tobytes()
    stride = alpha.bytesPerLine()
    rows = [y for y in range(h) if max(data[y * stride:y * stride + w]) > 16]
    cols = [x for x in range(w) if any(data[y * stride + x] > 16 for y in rows[::2])]
    return QRect(cols[0], rows[0], cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1)


def main(out_dir, pairs):
    os.makedirs(out_dir, exist_ok=True)
    frames = {}
    for pair in pairs:
        name, path = pair.split("=", 1)
        img = QImage(path)
        if img.isNull():
            print("skip (cannot read):", path)
            continue
        corner = img.pixelColor(0, 0)
        if not img.hasAlphaChannel() or corner.alpha() == 255:
            img = clear_background(img)
        frames[name] = img.copy(opaque_bounds(img))
    if not frames:
        return
    ratio = min(1.0, MAX_H / max(f.height() for f in frames.values()))
    for name, img in frames.items():
        w, h = max(1, round(img.width() * ratio)), max(1, round(img.height() * ratio))
        out = os.path.join(out_dir, name + ".png")
        img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(out, "PNG", 9)
        print(f"{out}: {w}x{h}, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
