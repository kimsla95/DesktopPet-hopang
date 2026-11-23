import random
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from .config import ALL_DAYS


class Scheduler(QObject):
    """Wakes once per minute for alarms and once per random interval for cheers."""

    alarm = Signal(str)
    cheer = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._last_minute = None
        self._minute_timer = QTimer(self, singleShot=True, timeout=self._on_minute)
        self._minute_timer.setTimerType(Qt.PreciseTimer)
        self._cheer_timer = QTimer(self, singleShot=True, timeout=self._on_cheer)
        self._arm_minute()
        self.reset_cheer()

    def _arm_minute(self):
        now = datetime.now()
        ms = (60 - now.second) * 1000 - now.microsecond // 1000 + 200
        self._minute_timer.start(ms)

    def _on_minute(self):
        now = datetime.now()
        key = now.strftime("%Y%m%d%H%M")
        if key != self._last_minute:
            self._last_minute = key
            hm, weekday = now.strftime("%H:%M"), now.weekday()
            for a in self.settings["alarms"]:
                if a.get("enabled", True) and a.get("time") == hm and weekday in a.get("days", ALL_DAYS):
                    self.alarm.emit(a.get("message", ""))
        self._arm_minute()

    def reset_cheer(self):
        c = self.settings["cheer"]
        lo = max(1, int(c.get("min_minutes", 30)))
        hi = max(lo, int(c.get("max_minutes", 120)))
        self._cheer_timer.start(random.randint(lo * 60, hi * 60) * 1000)

    def _on_cheer(self):
        if self.settings["cheer"].get("enabled", True) and not self.in_quiet_time():
            self.cheer.emit()
        self.reset_cheer()

    def in_quiet_time(self):
        q = self.settings["quiet"]
        if not q.get("enabled"):
            return False
        now, start, end = datetime.now().strftime("%H:%M"), q.get("start", "22:00"), q.get("end", "08:00")
        if start <= end:
            return start <= now < end
        return now >= start or now < end
