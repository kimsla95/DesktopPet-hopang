"""Updater test against a local fake GitHub API (no internet needed). Uses a temp APPDATA/TEMP."""
import hashlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["APPDATA"] = tempfile.mkdtemp()
tempfile.tempdir = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pet"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
from app import config, semver, updater  # noqa: E402

INSTALLER = os.urandom(3 * 1024 * 1024)
GOOD_SHA = hashlib.sha256(INSTALLER).hexdigest()
state = {"tag": "v1.1.0", "sha": GOOD_SHA, "status": 200, "hits": []}


class FakeGitHub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        state["hits"].append(self.path)
        port = self.server.server_port
        if self.path == "/repos/me/pet/releases/latest":
            if state["status"] != 200:
                return self._send(state["status"], b"{}")
            body = {
                "tag_name": state["tag"], "body": "- 캐릭터 이동 기능 개선\n- 알림 오류 수정",
                "assets": [
                    {"name": "DesktopPet-Setup-1.1.0.exe", "size": len(INSTALLER),
                     "browser_download_url": f"http://127.0.0.1:{port}/dl/setup.exe"},
                    {"name": "DesktopPet-Setup-1.1.0.exe.sha256",
                     "browser_download_url": f"http://127.0.0.1:{port}/dl/setup.exe.sha256"},
                ],
            }
            return self._send(200, json.dumps(body).encode())
        if self.path == "/dl/setup.exe":
            self.send_response(302)                      # GitHub redirects downloads to a CDN
            self.send_header("Location", "/cdn/setup.exe")
            self.end_headers()
            return
        if self.path == "/cdn/setup.exe":
            return self._send(200, INSTALLER, "application/octet-stream")
        if self.path == "/dl/setup.exe.sha256":
            return self._send(200, f"{state['sha']} *DesktopPet-Setup-1.1.0.exe\n".encode())
        self._send(404, b"")

    def _send(self, code, data, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
threading.Thread(target=server.serve_forever, daemon=True).start()
updater.API = f"http://127.0.0.1:{server.server_port}"
updater.STARTUP_DELAY_SEC = 0.2

launched = []
updater.QProcess.startDetached = staticmethod(lambda path, args: launched.append((path, list(args))) or True)

steps = []


def check(name, cond):
    steps.append((name, bool(cond)))


# ---- pure functions --------------------------------------------------------
check("semver 1.1.0 > 1.0.0", semver.is_newer("1.1.0", "1.0.0"))
check("semver 1.0.10 > 1.0.9 (not string compare)", semver.is_newer("1.0.10", "1.0.9"))
check("semver 2.0.0 > 1.99.99", semver.is_newer("v2.0.0", "1.99.99"))
check("semver equal is not newer", not semver.is_newer("1.0.0", "v1.0.0"))
check("semver older is not newer", not semver.is_newer("1.0.0", "1.0.1"))
check("semver release > prerelease", semver.is_newer("1.0.0", "1.0.0-beta.2"))
check("semver beta.11 > beta.2", semver.is_newer("1.0.0-beta.11", "1.0.0-beta.2"))
check("semver junk ignored", not semver.is_newer("latest", "1.0.0"))
check("repo formats", [updater.parse_repo(r) for r in
                       ("me/pet", "https://github.com/me/pet", "https://github.com/me/pet.git/", "x", "")]
      == ["me/pet", "me/pet", "me/pet", "", ""])

os.makedirs(updater.download_dir())
open(os.path.join(updater.download_dir(), "old-setup.exe"), "wb").write(b"x")

# ---- app flow ----------------------------------------------------------------
settings = config.load()
settings["update"]["repo"] = "me/pet"
config.save(settings)
qapp = QApplication(sys.argv)
qapp.setQuitOnLastWindowClosed(False)  # same as main.main()
app = main.App(qapp)
quit_calls = []
app.quit = lambda: quit_calls.append(1)
check("old downloads cleaned at start", not os.path.exists(updater.download_dir()))
check("startup not blocked (check is deferred)", app.updater.timer.isActive() and not state["hits"])


def wait_for(cond, then, timeout=8000, name="wait"):
    left = [timeout // 50]

    def poll():
        if cond():
            then()
        elif left[0] <= 0:
            check(name + " (timed out)", False)
            report()
        else:
            left[0] -= 1
            QTimer.singleShot(50, poll)
    poll()


def t_popup():
    dlg = app.update_dialog
    check("popup shown for 1.1.0", dlg is not None and "1.1.0" in dlg.info.text())
    check("release notes shown", dlg and "알림 오류 수정" in dlg.notes.toPlainText())
    check("last_check saved", config.load()["update"]["last_check"] > 0)
    dlg.later_btn.click()
    check("'나중에' closes, app keeps running", app.update_dialog is None and not quit_calls)
    check("next check scheduled later (>= 1h)", app.updater.timer.remainingTime() > 3500 * 1000)
    state["sha"] = "0" * 64
    app.updater.check(manual=True)
    wait_for(lambda: app.update_dialog is not None, t_bad_checksum, name="popup again")


def t_bad_checksum():
    dlg = app.update_dialog
    progress = []
    app.updater.progress.connect(lambda d, t: progress.append(d))
    dlg.now_btn.click()
    wait_for(lambda: dlg.later_btn.text() == "닫기",
             lambda: after_bad(dlg, progress), name="bad checksum result")


def after_bad(dlg, progress):
    check("bad checksum -> refused", "검증에 실패" in dlg.status.text() and not launched)
    check("bad file deleted", not os.listdir(updater.download_dir()))
    check("progress reported", len(progress) > 0)
    dlg.later_btn.click()
    state["sha"] = GOOD_SHA
    app.updater.check(manual=True)
    wait_for(lambda: app.update_dialog is not None, t_good, name="popup 3")


def t_good():
    dlg = app.update_dialog
    values = []
    app.updater.progress.connect(lambda d, t: values.append(dlg.bar.value()))
    dlg.now_btn.click()
    wait_for(lambda: launched, lambda: after_good(values), name="installer launch")


def after_good(values):
    path, args = launched[0]
    check("progress bar reached 100", values and max(values) == 100)
    check("verified installer saved in temp", os.path.isfile(path) and path.startswith(updater.download_dir())
          and hashlib.sha256(open(path, "rb").read()).hexdigest() == GOOD_SHA)
    check("installer runs silently", args == updater.INSTALLER_ARGS)
    QTimer.singleShot(200, after_launch)


def after_launch():
    check("app quits for install", quit_calls == [1] and app.update_dialog is None)
    state["tag"] = "v1.0.0"
    notices = []
    main.QMessageBox.information = staticmethod(lambda *a: notices.append(a[2]))
    app.updater.check(manual=True)
    wait_for(lambda: notices, lambda: t_same(notices), name="no-update notice")


def t_same(notices):
    check("same version -> no popup, '최신 버전' notice", app.update_dialog is None and "최신" in notices[0])
    state["status"] = 404
    notices.clear()
    app.updater.check(manual=True)
    wait_for(lambda: notices, lambda: t_404(notices), name="404 notice")


def t_404(notices):
    check("no releases yet (404) handled", app.update_dialog is None and "최신" in notices[0])
    server.shutdown()
    server.server_close()
    notices.clear()
    app.updater.check(manual=False)
    wait_for(lambda: app.updater._check_reply is None, lambda: t_offline(notices), name="offline check")


def t_offline(notices):
    check("offline auto-check: silent, no popup", not notices and app.update_dialog is None)
    check("offline: quiet retry in ~1h", 3000 * 1000 < app.updater.timer.remainingTime() <= 3600 * 1000)
    app.updater.check(manual=True)
    wait_for(lambda: notices, lambda: t_offline_manual(notices), name="offline manual")


def t_offline_manual(notices):
    check("offline manual check explains error", "인터넷" in notices[0])
    app.settings["update"]["enabled"] = False
    app.updater.reschedule()
    check("disabled -> no scheduled checks", not app.updater.timer.isActive())
    check("pet still alive", app.pet.isVisible())
    report()


def report():
    for name, ok in steps:
        print(("OK  " if ok else "FAIL") + " " + name)
    qapp.exit(0 if all(ok for _, ok in steps) else 1)


wait_for(lambda: app.update_dialog is not None, t_popup, name="auto check popup")
sys.exit(qapp.exec())
