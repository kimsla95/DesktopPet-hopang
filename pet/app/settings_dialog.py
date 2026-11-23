import copy

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTimeEdit, QVBoxLayout,
)

from .config import ALL_DAYS

DAY_NAMES = "월화수목금토일"


def days_text(days):
    days = sorted(set(days))
    if days == ALL_DAYS:
        return "매일"
    if days == [0, 1, 2, 3, 4]:
        return "평일"
    if days == [5, 6]:
        return "주말"
    return "".join(DAY_NAMES[d] for d in days) or "없음"


def time_edit(text):
    edit = QTimeEdit(QTime.fromString(text, "HH:mm"))
    edit.setDisplayFormat("HH:mm")
    return edit


class AlarmDialog(QDialog):
    def __init__(self, parent, alarm=None):
        super().__init__(parent)
        self.setWindowTitle("알림")
        alarm = alarm or {"time": "09:00", "message": "", "enabled": True, "days": ALL_DAYS}
        self.time = time_edit(alarm["time"])
        self.message = QLineEdit(alarm["message"])
        self.message.setMaxLength(60)
        self.enabled = QCheckBox("사용")
        self.enabled.setChecked(alarm.get("enabled", True))
        days_row = QHBoxLayout()
        self.day_boxes = []
        for i, name in enumerate(DAY_NAMES):
            box = QCheckBox(name)
            box.setChecked(i in alarm.get("days", ALL_DAYS))
            days_row.addWidget(box)
            self.day_boxes.append(box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("시간", self.time)
        form.addRow("메시지", self.message)
        form.addRow("요일", days_row)
        form.addRow("", self.enabled)
        form.addRow(buttons)

    def _accept(self):
        if not self.message.text().strip():
            QMessageBox.warning(self, "알림", "메시지를 입력해 주세요.")
        elif not any(b.isChecked() for b in self.day_boxes):
            QMessageBox.warning(self, "알림", "요일을 하나 이상 선택해 주세요.")
        else:
            self.accept()

    def value(self):
        return {
            "time": self.time.time().toString("HH:mm"),
            "message": self.message.text().strip(),
            "enabled": self.enabled.isChecked(),
            "days": [i for i, b in enumerate(self.day_boxes) if b.isChecked()],
        }


class SettingsDialog(QDialog):
    def __init__(self, settings, reset_position, version="", check_now=None):
        super().__init__()
        self.setWindowTitle("알림 설정")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.alarms = copy.deepcopy(settings["alarms"])

        # alarms
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["시간", "메시지", "요일", "사용"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._toggled)
        self.table.doubleClicked.connect(self._edit)

        add_btn, edit_btn, del_btn = QPushButton("추가"), QPushButton("수정"), QPushButton("삭제")
        add_btn.clicked.connect(self._add)
        edit_btn.clicked.connect(self._edit)
        del_btn.clicked.connect(self._delete)
        btn_row = QHBoxLayout()
        for b in (add_btn, edit_btn, del_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()

        alarm_box = QGroupBox("알림")
        alarm_layout = QVBoxLayout(alarm_box)
        alarm_layout.addWidget(self.table)
        alarm_layout.addLayout(btn_row)

        # random cheer
        cheer = settings["cheer"]
        self.cheer_on = QCheckBox("랜덤 응원 사용")
        self.cheer_on.setChecked(cheer.get("enabled", True))
        self.cheer_min = self._minutes(cheer.get("min_minutes", 30))
        self.cheer_max = self._minutes(cheer.get("max_minutes", 120))
        cheer_box = QGroupBox("랜덤 응원")
        cheer_form = QFormLayout(cheer_box)
        cheer_form.addRow(self.cheer_on)
        cheer_form.addRow("최소 간격", self.cheer_min)
        cheer_form.addRow("최대 간격", self.cheer_max)

        # quiet time
        quiet = settings["quiet"]
        self.quiet_on = QCheckBox("조용한 시간 사용 (랜덤 응원 끔)")
        self.quiet_on.setChecked(quiet.get("enabled", True))
        self.quiet_start = time_edit(quiet.get("start", "22:00"))
        self.quiet_end = time_edit(quiet.get("end", "08:00"))
        quiet_box = QGroupBox("조용한 시간")
        quiet_form = QFormLayout(quiet_box)
        quiet_form.addRow(self.quiet_on)
        quiet_form.addRow("시작", self.quiet_start)
        quiet_form.addRow("종료", self.quiet_end)

        # character
        self.size_spin = QSpinBox()
        self.size_spin.setRange(80, 300)
        self.size_spin.setSingleStep(10)
        self.size_spin.setSuffix(" px")
        self.size_spin.setValue(int(settings.get("size") or 150))
        reset_btn = QPushButton("위치 초기화")
        reset_btn.clicked.connect(reset_position)
        char_box = QGroupBox("캐릭터")
        char_form = QFormLayout(char_box)
        char_form.addRow("크기", self.size_spin)
        char_form.addRow(reset_btn)

        # update
        upd = settings.get("update", {})
        self.update_prefs = dict(upd)
        self.update_on = QCheckBox("시작할 때 업데이트 확인")
        self.update_on.setChecked(upd.get("enabled", True))
        self.update_hours = QSpinBox()
        self.update_hours.setRange(1, 168)
        self.update_hours.setSuffix(" 시간")
        self.update_hours.setValue(int(upd.get("interval_hours", 6)))
        check_btn = QPushButton("지금 확인")
        check_btn.setEnabled(check_now is not None)
        if check_now:
            check_btn.clicked.connect(check_now)
        update_box = QGroupBox("업데이트")
        update_form = QFormLayout(update_box)
        update_form.addRow("현재 버전", QLabel(version or "-"))
        update_form.addRow(self.update_on)
        update_form.addRow("확인 주기", self.update_hours)
        update_form.addRow(check_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("저장")
        buttons.button(QDialogButtonBox.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        side = QVBoxLayout()
        for box in (cheer_box, quiet_box, char_box, update_box):
            side.addWidget(box)
        side.addStretch()
        body = QHBoxLayout()
        body.addWidget(alarm_box, 1)
        body.addLayout(side)
        root = QVBoxLayout(self)
        root.addLayout(body)
        root.addWidget(buttons)

        self.resize(640, 360)
        self._refresh()

    @staticmethod
    def _minutes(value):
        spin = QSpinBox()
        spin.setRange(1, 1440)
        spin.setSuffix(" 분")
        spin.setValue(int(value))
        return spin

    def _refresh(self):
        self.alarms.sort(key=lambda a: a["time"])
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.alarms))
        for row, a in enumerate(self.alarms):
            for col, text in enumerate((a["time"], a["message"], days_text(a.get("days", ALL_DAYS)))):
                self.table.setItem(row, col, QTableWidgetItem(text))
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            on.setCheckState(Qt.Checked if a.get("enabled", True) else Qt.Unchecked)
            self.table.setItem(row, 3, on)
        self.table.blockSignals(False)

    def _toggled(self, item):
        if item.column() == 3:
            self.alarms[item.row()]["enabled"] = item.checkState() == Qt.Checked

    def _add(self):
        dlg = AlarmDialog(self)
        if dlg.exec():
            self.alarms.append(dlg.value())
            self._refresh()

    def _edit(self):
        row = self.table.currentRow()
        if row < 0:
            return
        dlg = AlarmDialog(self, self.alarms[row])
        if dlg.exec():
            self.alarms[row] = dlg.value()
            self._refresh()

    def _delete(self):
        row = self.table.currentRow()
        if row >= 0:
            del self.alarms[row]
            self._refresh()

    def result_settings(self):
        lo, hi = sorted((self.cheer_min.value(), self.cheer_max.value()))
        return {
            "size": self.size_spin.value(),
            "alarms": self.alarms,
            "cheer": {"enabled": self.cheer_on.isChecked(), "min_minutes": lo, "max_minutes": hi},
            "quiet": {
                "enabled": self.quiet_on.isChecked(),
                "start": self.quiet_start.time().toString("HH:mm"),
                "end": self.quiet_end.time().toString("HH:mm"),
            },
            "update": {**self.update_prefs, "enabled": self.update_on.isChecked(),
                       "interval_hours": self.update_hours.value()},
        }
