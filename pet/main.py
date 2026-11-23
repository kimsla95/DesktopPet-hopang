import sys

from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from app import config
from app.character import Character
from app.pet import PetWindow
from app.roam import Roamer
from app.scheduler import Scheduler
from app.settings_dialog import SettingsDialog
from app.update_dialog import UpdateDialog
from app.updater import Updater


class App:
    def __init__(self, qapp):
        self.qapp = qapp
        self.info = config.app_info()
        self.settings = config.load()
        self.character = Character(self.settings.get("character", "hobang"))
        self.pet = PetWindow(self.settings, self.character)
        self.scheduler = Scheduler(self.settings)
        self.dialog = None

        self.pet.settings_requested.connect(self.open_settings)
        self.pet.quit_requested.connect(self.quit)
        self.scheduler.alarm.connect(self.pet.alarm)
        self.scheduler.cheer.connect(self.pet.random_cheer)

        # One checkable action shared by the pet's right-click menu and the tray menu.
        self.roamer = Roamer(self.pet)
        self.pet.hold_started.connect(self.roamer.pause)
        self.pet.hold_finished.connect(self.roamer.resume)
        self.roam_action = QAction(qapp, checkable=True)
        self.roam_action.toggled.connect(self.set_roam)
        self.pet.roam_action = self.roam_action

        # Tray icon is the only way back after "캐릭터 숨기기".
        self.tray_menu = QMenu()
        self.tray_menu.addAction(self.roam_action)
        self.tray_menu.addAction("캐릭터 보이기", self.pet.show)
        self.tray_menu.addAction("알림 설정", self.open_settings)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("종료", self.quit)
        self.tray = QSystemTrayIcon(self.character.icon(), qapp)
        self.tray.setToolTip(f"{self.character.name} v{self.info['version']}")
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.pet.show()
        roam = bool(self.settings.get("roam", False))
        self.roam_action.blockSignals(True)
        self.roam_action.setChecked(roam)
        self.roam_action.blockSignals(False)
        self.set_roam(roam)

        self.update_dialog = None
        self.updater = Updater(self.settings, self.info["version"], self.info["repo"])
        self.updater.update_available.connect(self.show_update)
        self.updater.no_update.connect(lambda: self._notice("지금 최신 버전을 쓰고 있어요!"))
        self.updater.check_failed.connect(self._notice)
        self.updater.start()

    def show_update(self, release):
        if self.update_dialog:
            return
        self.update_dialog = dlg = UpdateDialog(self.updater, release, self.info["version"], self.character.icon())
        if QApplication.activeModalWidget():
            dlg.setWindowModality(Qt.ApplicationModal)
        dlg.finished.connect(self._update_closed)
        dlg.show()

    def _update_closed(self):
        installing = self.update_dialog.installing
        self.update_dialog = None
        if installing:
            self.quit()

    def _notice(self, text):
        QMessageBox.information(QApplication.activeModalWidget(), "업데이트", text)

    def set_roam(self, on):
        self.roam_action.setText("방목 ON" if on else "방목 OFF")
        if self.settings.get("roam") != on:
            self.settings["roam"] = on
            config.save(self.settings)
        self.roamer.set_enabled(on)
        if not on:
            self.pet.save_position()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.pet.show()
            self.pet.raise_()

    def open_settings(self):
        if self.dialog:
            self.dialog.activateWindow()
            return
        self.dialog = SettingsDialog(self.settings, self.pet.reset_position, self.info["version"],
                                     lambda: self.updater.check(manual=True))
        if self.dialog.exec():
            self.settings.update(self.dialog.result_settings())
            config.save(self.settings)
            self.pet.apply_size(self.settings["size"])
            self.scheduler.reset_cheer()
            self.updater.reschedule()
        self.dialog = None

    def quit(self):
        self.pet.save_position()
        self.tray.hide()
        self.qapp.quit()


def main():
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    app = App(qapp)  # noqa: F841 - keep references alive
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
