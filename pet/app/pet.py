import math
import random

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMenu, QWidget

from . import config

PAD = 18          # room around the image for bobbing / reactions
IDLE_MS = 120     # idle bob tick (~8 fps, repaints only when the offset changes)
REACT_MS = 33
REACT_SEC = 0.8
WALK_MS = 200     # walk frame swap interval while the character is actually moving


def screen_rect(point):
    screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


class Bubble(QWidget):
    TAIL = 10
    MAX_TEXT_W = 220

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        self.text = ""
        self.tail_up = False
        self.tail_x = 0
        self.body = QRect()
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def say(self, text, anchor, ms):
        self.text = text
        self.place(anchor)
        self.show()
        self.raise_()
        self.update()
        self.timer.start(ms)

    def place(self, anchor):
        """Put the bubble above the character (below if there is no room)."""
        tr = QFontMetrics(self.font()).boundingRect(
            QRect(0, 0, self.MAX_TEXT_W, 1000), Qt.TextWordWrap | Qt.AlignCenter, self.text)
        w = max(tr.width() + 28, 64)
        body_h = tr.height() + 18
        h = body_h + self.TAIL
        area = screen_rect(anchor.center())
        x = anchor.center().x() - w // 2
        y = anchor.top() - h + 4
        self.tail_up = y < area.top()
        if self.tail_up:
            y = anchor.bottom() - 4
        x = max(area.left(), min(x, area.right() - w + 1))
        self.tail_x = max(16, min(anchor.center().x() - x, w - 16))
        self.body = QRect(0, self.TAIL if self.tail_up else 0, w, body_h)
        self.setGeometry(x, y, w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QRectF(self.body).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(body, 12, 12)
        tail = QPainterPath()
        tx = self.tail_x
        if self.tail_up:
            tail.moveTo(tx - 8, body.top() + 2)
            tail.lineTo(tx, 1)
            tail.lineTo(tx + 8, body.top() + 2)
        else:
            tail.moveTo(tx - 8, body.bottom() - 2)
            tail.lineTo(tx, self.height() - 1)
            tail.lineTo(tx + 8, body.bottom() - 2)
        tail.closeSubpath()
        p.setPen(QPen(QColor("#8B5A2B"), 2))
        p.setBrush(QColor("#FFFDF7"))
        p.drawPath(path.united(tail))
        p.setPen(QColor("#4A3020"))
        p.drawText(body.adjusted(10, 0, -10, 0), Qt.TextWordWrap | Qt.AlignCenter, self.text)

    def mousePressEvent(self, _):
        self.timer.stop()
        self.hide()


class PetWindow(QWidget):
    settings_requested = Signal()
    quit_requested = Signal()
    hold_started = Signal()    # user grabbed the pet (press / menu); autonomous moves must pause
    hold_finished = Signal()

    def __init__(self, settings, character):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.settings = settings
        self.char = character
        self.bubble = Bubble()
        self.frames = {}
        self.size_px = 0
        self.face = "idle"
        self.frame_index = 0
        self.facing_left = False
        self.walk_clock = QElapsedTimer()
        self.bob = 0
        self.phase = 0.0
        self.reaction = None
        self.react_t = 0.0
        self.drag_offset = None
        self.press_pos = QPoint()
        self.dragged = False
        self.roam_action = None

        self.idle_timer = QTimer(self, interval=IDLE_MS, timeout=self._idle_tick)
        self.react_timer = QTimer(self, interval=REACT_MS, timeout=self._react_tick)
        self.blink_timer = QTimer(self, singleShot=True, timeout=self._blink)
        self.walk_stop_timer = QTimer(self, singleShot=True, interval=WALK_MS + 50, timeout=self._stop_walking)

        self.apply_size(settings.get("size") or character.default_size)
        pos = settings.get("pos")
        self.move(self.clamp(QPoint(*pos) if pos else self.default_pos()))

    # ---- size / position -------------------------------------------------
    def apply_size(self, size):
        self.size_px = max(60, min(int(size), 400))
        self.frames = self.char.frames(self.size_px, self.devicePixelRatioF())
        self.setFixedSize(self.size_px + PAD * 2, self.size_px + PAD * 2)
        self.move(self.clamp(self.pos()))
        self.update()

    def default_pos(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(g.right() - self.width() - 40, g.bottom() - self.height() - 40)

    def clamp(self, p):
        g = screen_rect(p + QPoint(self.width() // 2, self.height() // 2))
        x = max(g.left() - PAD, min(p.x(), g.right() + 1 + PAD - self.width()))
        y = max(g.top() - PAD, min(p.y(), g.bottom() + 1 + PAD - self.height()))
        return QPoint(x, y)

    def reset_position(self):
        self.move(self.clamp(self.default_pos()))
        self.save_position()

    def save_position(self):
        self.settings["pos"] = [self.x(), self.y()]
        config.save(self.settings)

    def move_to(self, p):
        self.move(p)
        if self.bubble.isVisible():
            self.bubble.place(self.anchor())

    def anchor(self):
        return QRect(self.mapToGlobal(QPoint(PAD, PAD)), QSize(self.size_px, self.size_px))

    # ---- timers ----------------------------------------------------------
    def showEvent(self, e):
        self.idle_timer.start()
        self._schedule_blink()
        super().showEvent(e)

    def hideEvent(self, e):
        self.idle_timer.stop()
        self.blink_timer.stop()
        self.bubble.hide()
        super().hideEvent(e)

    def _idle_tick(self):
        self.phase = (self.phase + IDLE_MS / 3000) % 1.0
        bob = round(3 * math.sin(self.phase * 2 * math.pi))
        if bob != self.bob and self.reaction is None and self.face == "idle":
            self.bob = bob
            self.update()

    def _schedule_blink(self):
        if "blink" in self.frames:
            self.blink_timer.start(random.randint(2500, 6000))

    def _blink(self):
        if self.reaction is None and self.face == "idle":
            self.set_state("blink")
            QTimer.singleShot(150, self._unblink)
        else:
            self._schedule_blink()

    def _unblink(self):
        if self.face == "blink":
            self.set_state("idle")
        if self.isVisible():
            self._schedule_blink()

    def set_state(self, state):
        """Switch the displayed image set (idle / walk / fly / ...); unknown states fall back to idle."""
        state = state if state in self.frames else "idle"
        if state != self.face:
            self.face = state
            self.frame_index = 0
            self.update()

    def react(self, kind):
        self.reaction = kind
        self.react_t = 0.0
        self.set_state("happy")
        self.react_timer.start()
        self.update()

    def _react_tick(self):
        self.react_t += REACT_MS / 1000
        if self.react_t >= REACT_SEC:
            self.react_timer.stop()
            self.reaction = None
            if self.face == "happy":
                self.set_state("idle")
        self.update()

    def _walk_step(self, dx):
        """Called only when the window really moved, so frames advance in step with the movement."""
        facing_left = dx < 0 if dx else self.facing_left
        if self.face != "walk":
            self.set_state("walk")
            self.walk_clock.start()
        elif self.walk_clock.elapsed() >= WALK_MS:
            self.frame_index += 1
            self.walk_clock.start()
            self.update()
        if facing_left != self.facing_left:
            self.facing_left = facing_left
            self.update()
        self.walk_stop_timer.start()

    def _stop_walking(self):
        self.walk_stop_timer.stop()
        self.facing_left = False
        if self.face == "walk":
            self.set_state("idle")
        self.update()

    # ---- painting --------------------------------------------------------
    def paintEvent(self, _):
        frames = self.frames.get(self.face) or self.frames["idle"]
        pm = frames[self.frame_index % len(frames)]
        size = pm.deviceIndependentSize()
        w, h = size.width(), size.height()
        p = QPainter(self)
        bob = self.bob if self.face == "idle" else 0
        if self.reaction is None and not self.facing_left:
            p.drawPixmap(QPointF((self.width() - w) / 2, PAD + self.size_px - h + bob), pm)
            return
        rot, sx, sy, dy = 0.0, 1.0, 1.0, bob
        if self.reaction:
            t = self.react_t
            decay = 1 - t / REACT_SEC
            if self.reaction == "pet":
                rot = 7 * math.sin(t * 22) * decay
            elif self.reaction == "feed":
                s = abs(math.sin(t * 16)) * decay
                sx, sy = 1 + 0.08 * s, 1 - 0.12 * s
            elif self.reaction == "jump":
                dy = -14 * abs(math.sin(t * 2 * math.pi / REACT_SEC))
            p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(self.width() / 2, PAD + self.size_px + dy)
        p.rotate(rot)
        p.scale(-sx if self.facing_left else sx, sy)
        p.drawPixmap(QRectF(-w / 2, -h, w, h), pm, QRectF(pm.rect()))

    # ---- mouse -----------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press_pos = e.globalPosition().toPoint()
            self.drag_offset = self.press_pos - self.pos()
            self.dragged = False
            self.hold_started.emit()

    def mouseMoveEvent(self, e):
        if self.drag_offset is None or not (e.buttons() & Qt.LeftButton):
            return
        g = e.globalPosition().toPoint()
        if not self.dragged and (g - self.press_pos).manhattanLength() < 5:
            return
        self.dragged = True
        target = self.clamp(g - self.drag_offset)
        dx = target.x() - self.x()
        if target == self.pos():
            return
        self.move_to(target)
        self._walk_step(dx)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.drag_offset is None:
            return
        self.drag_offset = None
        if self.dragged:
            self._stop_walking()
            self.save_position()
        else:
            self.pet()
        self.hold_finished.emit()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.addAction("쓰다듬기", self.pet)
        menu.addAction("밥 먹이기", self.feed)
        menu.addAction("응원받기", self.cheer)
        menu.addSeparator()
        if self.roam_action:
            menu.addAction(self.roam_action)
        menu.addAction("알림 설정", self.settings_requested.emit)
        menu.addAction("캐릭터 숨기기", self.hide)
        menu.addSeparator()
        menu.addAction("종료", self.quit_requested.emit)
        self.hold_started.emit()
        menu.exec(e.globalPos())
        menu.deleteLater()
        self.hold_finished.emit()

    # ---- actions ---------------------------------------------------------
    def say(self, text, ms=3500):
        if self.isVisible():
            self.bubble.say(text, self.anchor(), ms)

    def pet(self):
        self.react("pet")
        self.say(self.char.line("pet"))

    def feed(self):
        self.react("feed")
        self.say(self.char.line("feed"))

    def cheer(self):
        self.react("jump")
        self.say(self.char.line("cheer"))

    def random_cheer(self):
        if self.isVisible():
            self.react("jump")
            self.say(self.char.line("cheer"), 6000)

    def alarm(self, message):
        if not self.isVisible():
            self.show()
        self.raise_()
        self.react("jump")
        self.say(message, 30000)
