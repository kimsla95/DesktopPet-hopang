import math
import random

from PySide6.QtCore import QElapsedTimer, QObject, QPointF, QRectF, QTimer

from .pet import PAD, screen_rect

TICK_MS = 40              # movement tick, only while a move is in progress
WAIT_SEC = (4.0, 15.0)    # pause between moves
REST_CHANCE = 0.25        # sometimes skip a move and just keep resting
FLY_CHANCE = 0.3
WALK_SPEED = (35, 80)     # px/s
WALK_DIST = (80, 360)
FLY_SPEED = (110, 190)
FLY_DIST = (150, 600)


class Roamer(QObject):
    """'방목' mode: the pet wanders on its own. Two timers created once; both stopped while off."""

    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.enabled = False
        self.paused = False
        self.mode = None
        self.pos = QPointF()
        self.target = QPointF()
        self.speed = 0.0
        self.clock = QElapsedTimer()
        self.wait_timer = QTimer(self, singleShot=True, timeout=self._start_move)
        self.move_timer = QTimer(self, interval=TICK_MS, timeout=self._tick)

    # ---- control -----------------------------------------------------------
    def set_enabled(self, on):
        self.enabled = on
        if on and not self.paused:
            self._wait()
        elif not on:
            self._halt()

    def pause(self):
        """User is holding the pet (drag / click / menu): no autonomous movement."""
        self.paused = True
        self._halt()

    def resume(self):
        self.paused = False
        if self.enabled:
            self._wait()

    def _halt(self):
        self.wait_timer.stop()
        if self.mode:
            self._end_move()

    def _wait(self):
        self.wait_timer.start(int(random.uniform(*WAIT_SEC) * 1000))

    # ---- movement ----------------------------------------------------------
    def _bounds(self):
        """Allowed range for the window's top-left on the pet's current screen."""
        pet = self.pet
        g = screen_rect(pet.geometry().center())
        return QRectF(g.left() - PAD, g.top() - PAD,
                      g.width() + 2 * PAD - pet.width(), g.height() + 2 * PAD - pet.height())

    def _start_move(self):
        pet = self.pet
        if not self.enabled or self.paused:
            return
        if not pet.isVisible() or pet.reaction or random.random() < REST_CHANCE:
            self._wait()
            return
        b = self._bounds()
        self.pos = QPointF(pet.pos())
        if "fly" in pet.frames and random.random() < FLY_CHANCE:
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(*FLY_DIST)
            x = self.pos.x() + math.cos(angle) * dist
            y = self.pos.y() + math.sin(angle) * dist
            if not b.left() <= x <= b.right():
                x = self.pos.x() - math.cos(angle) * dist   # bounce off the side
            if not b.top() <= y <= b.bottom():
                y = self.pos.y() - math.sin(angle) * dist
            self.mode, self.speed = "fly", random.uniform(*FLY_SPEED)
        else:
            dist = random.uniform(*WALK_DIST) * random.choice((-1, 1))
            x, y = self.pos.x() + dist, self.pos.y()
            if not b.left() <= x <= b.right():
                x = self.pos.x() - dist                     # turn around at the edge
            self.mode, self.speed = "walk", random.uniform(*WALK_SPEED)
        self.target = QPointF(min(max(x, b.left()), b.right()), min(max(y, b.top()), b.bottom()))
        if self.mode == "fly":
            pet.facing_left = self.target.x() < self.pos.x()
            pet.set_state("fly")
            pet.update()
        self.clock.start()
        self.move_timer.start()

    def _tick(self):
        pet = self.pet
        if not pet.isVisible():
            self._end_move()
            return
        step = self.speed * self.clock.restart() / 1000
        delta = self.target - self.pos
        dist = math.hypot(delta.x(), delta.y())
        arrived = dist <= step
        self.pos = QPointF(self.target) if arrived else self.pos + delta * (step / dist)
        new = pet.clamp(self.pos.toPoint())
        if new != pet.pos():
            dx = new.x() - pet.x()
            pet.move_to(new)
            if self.mode == "walk":
                pet._walk_step(dx)
        elif pet.clamp(self.target.toPoint()) == pet.pos():
            arrived = True                                  # pinned at an edge (e.g. screen changed)
        if arrived:
            self._end_move()
            pet.save_position()

    def _end_move(self):
        self.move_timer.stop()
        pet = self.pet
        if self.mode == "walk":
            pet._stop_walking()
        elif self.mode == "fly":
            pet.facing_left = False
            pet.set_state("idle")
            pet.update()
        self.mode = None
        if self.enabled and not self.paused:
            self._wait()
