"""Headless-ish smoke test: drives every feature once, then quits. Uses a temp APPDATA."""
import json
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pet"))

from PySide6.QtCore import QElapsedTimer, QEvent, QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QImage, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

import main  # noqa: E402
from app import config, roam  # noqa: E402
from app.character import Character  # noqa: E402
from app.settings_dialog import SettingsDialog  # noqa: E402

qapp = QApplication(sys.argv)
app = main.App(qapp)
pet = app.pet
steps = []


def check(name, cond):
    steps.append((name, bool(cond)))


def run():
    check("pet visible", pet.isVisible())
    check("frames loaded", [len(pet.frames.get(s, [])) for s in ("idle", "walk", "fly")] == [1, 2, 1])
    stand, walk = pet.frames["idle"][0], pet.frames["walk"][0]
    src = QImage(pet.char.paths["idle"][0])
    check("aspect kept", abs(stand.width() / stand.height() - src.width() / src.height()) < 0.02)
    check("same body scale", abs(stand.height() - walk.height()) <= 3)
    check("fits box", all(pm.deviceIndependentSize().width() <= pet.size_px + 0.5
                          and pm.deviceIndependentSize().height() <= pet.size_px + 0.5
                          for f in pet.frames.values() for pm in f))
    pet.set_state("fly")
    check("fly state", pet.face == "fly")
    pet.set_state("nope")
    check("unknown state -> idle", pet.face == "idle")

    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "ghost"))
    with open(os.path.join(tmp, "ghost", "config.json"), "w") as f:
        json.dump({"images": {"idle": "missing.png", "walk": ["nope.png"]}}, f)
    real_dirs = config.character_dirs
    config.character_dirs = lambda: [tmp]
    ghost = Character("ghost").frames(150, 1.0)
    config.character_dirs = real_dirs
    check("missing images -> placeholder", list(ghost) == ["idle"] and not ghost["idle"][0].isNull())
    check("unknown character -> default", Character("nobody").paths.get("walk"))
    pet.pet()
    check("pet bubble", pet.bubble.isVisible() and pet.bubble.text in pet.char.messages["pet"])
    pet.feed()
    check("feed bubble", pet.bubble.text in pet.char.messages["feed"])
    pet.cheer()
    check("cheer bubble", pet.bubble.text in pet.char.messages["cheer"])
    check("bubble above face", pet.bubble.geometry().bottom() <= pet.anchor().top() + 4
          or pet.bubble.geometry().top() >= pet.anchor().bottom() - 4)
    app.scheduler.alarm.emit("밥 먹자!")
    check("alarm bubble", pet.bubble.text == "밥 먹자!")
    pet.hide()
    check("hidden", not pet.isVisible())
    app.scheduler.alarm.emit("퇴근하자!")
    check("alarm reshows pet", pet.isVisible())

    dlg = SettingsDialog(app.settings, pet.reset_position)
    check("dialog rows", dlg.table.rowCount() == 3)
    dlg.alarms.append({"time": "15:00", "message": "스트레칭하자!", "enabled": False, "days": [0, 1, 2, 3, 4]})
    dlg.size_spin.setValue(120)
    app.settings.update(dlg.result_settings())
    config.save(app.settings)
    pet.apply_size(120)
    check("resized", pet.width() == 120 + 36)

    pet.move(-5000, -5000)
    pet.move(pet.clamp(pet.pos()))
    pet.save_position()
    saved = json.load(open(config.settings_path(), encoding="utf-8"))
    check("clamped on screen", saved["pos"][0] > -100 and saved["pos"][1] > -100)
    check("alarms saved", len(saved["alarms"]) == 4 and saved["size"] == 120)
    check("restore", config.load()["pos"] == saved["pos"])

    app.settings["quiet"] = {"enabled": True, "start": "00:00", "end": "23:59"}
    check("quiet time", app.scheduler.in_quiet_time())

    walk_test()


def mouse(kind, global_pos, buttons):
    local = QPointF(pet.mapFromGlobal(global_pos))
    ev = QMouseEvent(kind, local, QPointF(global_pos), Qt.LeftButton, buttons, Qt.NoModifier)
    QApplication.sendEvent(pet, ev)


def walk_test():
    """Drag left for ~1s at 25 ms steps, pause while holding, then release."""
    pet.move(800, 400)
    start = pet.pos() + QPoint(pet.width() // 2, pet.height() // 2)
    mouse(QEvent.MouseButtonPress, start, Qt.LeftButton)
    log = []
    clock = QElapsedTimer()
    clock.start()

    def step(i=0):
        if i < 40:
            mouse(QEvent.MouseMove, start - QPoint(4 * (i + 1), 0), Qt.LeftButton)
            log.append((clock.elapsed(), pet.face, pet.frame_index, pet.facing_left))
            QTimer.singleShot(25, lambda: step(i + 1))
        else:
            QTimer.singleShot(400, paused)

    def paused():
        del log[0]  # first 4 px move is below the 5 px drag threshold
        check("walking while moving", all(face == "walk" for _, face, _, _ in log))
        check("faces drag direction", all(left for *_, left in log))
        swaps = [t for (t, _, a, _), (_, _, b, _) in zip(log, log[1:]) if a != b]
        gaps = [b - a for a, b in zip(swaps, swaps[1:])]
        print("walk frame swaps (ms):", swaps, "gaps:", gaps)
        check("~200ms frame swaps", len(swaps) >= 3 and all(180 <= g <= 260 for g in gaps))
        check("stand when drag pauses", pet.face == "idle")
        mouse(QEvent.MouseButtonRelease, start - QPoint(160, 0), Qt.NoButton)
        check("stand after release", pet.face == "idle" and not pet.facing_left)
        check("drag saved position", config.load()["pos"] == [pet.x(), pet.y()])
        roam_test()

    step()


def roam_test():
    r = app.roamer
    check("roam off by default", not r.enabled and app.roam_action.text() == "방목 OFF"
          and not r.wait_timer.isActive() and not r.move_timer.isActive())
    app.roam_action.trigger()
    check("roam on", r.enabled and app.roam_action.text() == "방목 ON"
          and r.wait_timer.isActive() and config.load()["roam"] is True)

    roam.REST_CHANCE, roam.FLY_CHANCE = 0.0, 0.0
    pet.move(800, 400)
    before = pet.pos()
    r.wait_timer.stop()
    r._start_move()
    check("walk started", r.mode == "walk" and r.move_timer.isActive() and not r.wait_timer.isActive())

    def walking():
        check("walk moves horizontally", pet.x() != before.x() and pet.y() == before.y())
        check("walk animation", pet.face == "walk")
        check("walk target in bounds", r._bounds().contains(r.target))
        mouse(QEvent.MouseButtonPress, pet.geometry().center(), Qt.LeftButton)
        check("press pauses roam", r.paused and r.mode is None and not r.move_timer.isActive()
              and not r.wait_timer.isActive() and pet.face == "idle")
        held = pet.pos()
        QTimer.singleShot(300, lambda: held_check(held))

    def held_check(held):
        check("no auto move while held", pet.pos() == held)
        mouse(QEvent.MouseButtonRelease, pet.geometry().center(), Qt.NoButton)
        check("release resumes roam", not r.paused and r.wait_timer.isActive())
        QTimer.singleShot(1500, fly_start)  # let the click reaction finish

    def fly_start():
        roam.FLY_CHANCE = 1.0
        r.wait_timer.stop()
        r._start_move()
        check("fly started", r.mode == "fly" and pet.face == "fly")
        QTimer.singleShot(300, flying)

    def flying():
        check("fly target in bounds", r._bounds().contains(r.target))
        app.roam_action.trigger()
        stopped = pet.pos()
        check("off stops immediately", not r.enabled and r.mode is None and pet.face == "idle"
              and not r.move_timer.isActive() and not r.wait_timer.isActive()
              and app.roam_action.text() == "방목 OFF" and config.load()["roam"] is False)
        QTimer.singleShot(400, lambda: check("stays put when off", pet.pos() == stopped) or edge_test())

    def edge_test():
        b = r._bounds()
        pet.move(int(b.right()), 400)
        r.enabled = True
        ok = True
        for i in range(200):
            roam.FLY_CHANCE = i % 2
            r._start_move()
            ok &= b.contains(r.target)
            r.move_timer.stop()
            r.mode = None
        r.enabled = False
        r.wait_timer.stop()
        pet._stop_walking()
        pet.set_state("idle")
        check("edge: targets stay on screen (200 tries)", ok)
        roam.FLY_CHANCE, roam.REST_CHANCE = 1.0, 0.0
        r.enabled = True
        pet.move(800, 400)
        r._start_move()
        r.speed = 5000
        QTimer.singleShot(400, arrived)

    def arrived():
        check("arrival -> stand + next wait", r.mode is None and pet.face == "idle"
              and r.wait_timer.isActive() and config.load()["pos"] == [pet.x(), pet.y()])
        r.set_enabled(False)
        menus = len(pet.findChildren(QMenu))
        check("no leftover menus", menus == 0)
        report()

    QTimer.singleShot(600, walking)


def report():
    for name, ok in steps:
        print(("OK  " if ok else "FAIL") + " " + name)
    qapp.exit(0 if all(ok for _, ok in steps) else 1)


QTimer.singleShot(500, run)
sys.exit(qapp.exec())
