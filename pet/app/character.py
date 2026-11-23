import json
import os
import random

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from . import config

BODY_STATES = ("idle", "walk")  # these share one scale so the body never changes size between frames


class Character:
    """Reads characters/<key>/config.json; images stay on disk and are loaded only when (re)scaling."""

    def __init__(self, key):
        folder = self._find(key) or self._find(config.DEFAULTS["character"])
        cfg = {}
        if folder:
            try:
                with open(os.path.join(folder, "config.json"), encoding="utf-8") as f:
                    cfg = json.load(f)
            except (OSError, ValueError):
                cfg = {}
        self.name = cfg.get("name", key)
        self.default_size = cfg.get("default_size", 100)
        self.messages = cfg.get("messages", {})
        self.paths = {}
        for state, files in cfg.get("images", {}).items():
            files = [files] if isinstance(files, str) else files
            found = [os.path.join(folder, f) for f in files if os.path.isfile(os.path.join(folder, f))]
            if found:
                self.paths[state] = found

    @staticmethod
    def _find(key):
        for root in config.character_dirs():
            path = os.path.join(root, key)
            if os.path.isfile(os.path.join(path, "config.json")):
                return path
        return None

    @staticmethod
    def _placeholder():
        img = QImage(128, 128, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#FFF1D6"))
        p.setPen(QColor("#8B5A2B"))
        p.drawEllipse(8, 16, 112, 104)
        p.end()
        return img

    def _images(self):
        images = {}
        for state, paths in self.paths.items():
            loaded = [img for img in (QImage(p) for p in paths) if not img.isNull()]
            if loaded:
                images[state] = loaded
        if "idle" not in images:
            images["idle"] = [self._placeholder()]
        return images

    def frames(self, size, dpr):
        """Scaled pixmaps per state, fitting a size x size box with aspect ratio preserved."""
        images = self._images()
        body = [img for s in BODY_STATES for img in images.get(s, [])]
        body_ratio = size / max(max(img.width(), img.height()) for img in body)
        frames = {}
        for state, imgs in images.items():
            frames[state] = []
            for img in imgs:
                ratio = body_ratio if state in BODY_STATES else min(body_ratio, size / max(img.width(), img.height()))
                w, h = max(1, round(img.width() * ratio * dpr)), max(1, round(img.height() * ratio * dpr))
                pm = QPixmap.fromImage(img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                pm.setDevicePixelRatio(dpr)
                frames[state].append(pm)
        return frames

    def icon(self):
        path = self.paths.get("idle", [None])[0]
        return QIcon(path) if path else QIcon(QPixmap.fromImage(self._placeholder()))

    def line(self, kind):
        return random.choice(self.messages.get(kind) or ["!"])
