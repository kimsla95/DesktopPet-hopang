import json
import os
import re
import shutil
import tempfile
import time

from PySide6.QtCore import QCryptographicHash, QFile, QIODevice, QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import config, semver

API = "https://api.github.com"
USER_AGENT = b"DesktopPet-Updater"
TIMEOUT_MS = 30000                    # aborts when no data arrives for this long
RETRY_AFTER_FAIL_SEC = 3600           # quiet retry after a network error
STARTUP_DELAY_SEC = 5                 # never slow down startup
INSTALLER_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]


def parse_repo(text):
    """'owner/repo' or 'https://github.com/owner/repo(.git)' -> 'owner/repo' ('' if invalid)."""
    text = (text or "").strip().rstrip("/")
    if text.lower().endswith(".git"):
        text = text[:-4]
    text = re.sub(r"^(https?://)?(www\.)?github\.com/", "", text, flags=re.I)
    parts = text.split("/")
    if len(parts) == 2 and all(re.fullmatch(r"[\w.-]+", p) for p in parts):
        return "/".join(parts)
    return ""


def download_dir():
    return os.path.join(tempfile.gettempdir(), "DesktopPet-update")


def cleanup_downloads():
    shutil.rmtree(download_dir(), ignore_errors=True)


def pick_release(data):
    """GitHub 'latest release' JSON -> dict with what the updater needs, or None."""
    version = (data.get("tag_name") or "").lstrip("vV")
    if not semver.parse(version):
        return None
    assets = data.get("assets") or []
    exes = [a for a in assets if a.get("name", "").lower().endswith(".exe")]
    installer = next((a for a in exes if "setup" in a["name"].lower()), exes[0] if exes else None)
    if not installer:
        return None
    sha_name = installer["name"].lower() + ".sha256"
    sha_asset = next((a for a in assets if a.get("name", "").lower() == sha_name), None)
    digest = installer.get("digest") or ""
    return {
        "version": version,
        "notes": (data.get("body") or "").strip(),
        "file": installer["name"],
        "url": installer.get("browser_download_url", ""),
        "size": installer.get("size", 0),
        "sha_url": sha_asset.get("browser_download_url", "") if sha_asset else "",
        "sha256": digest[7:].lower() if digest.startswith("sha256:") else "",
    }


class Updater(QObject):
    update_available = Signal(dict)
    no_update = Signal()                 # manual checks only
    check_failed = Signal(str)           # manual checks only
    progress = Signal(int, int)
    downloaded = Signal(str)             # path of the verified installer
    download_failed = Signal(str)

    def __init__(self, settings, version, default_repo):
        super().__init__()
        self.settings = settings
        self.version = version
        self.default_repo = default_repo
        self._nam = None
        self._check_reply = None
        self._reply = None
        self._file = None
        self._hash = None
        self._expected = ""
        self._release = None
        self.timer = QTimer(self, singleShot=True, timeout=lambda: self.check(manual=False))

    # ---- settings ----------------------------------------------------------
    def prefs(self):
        return self.settings.setdefault("update", dict(config.DEFAULTS["update"]))

    def repo(self):
        return parse_repo(self.prefs().get("repo") or self.default_repo)

    def start(self):
        cleanup_downloads()
        self.reschedule()

    def reschedule(self, retry_sec=None):
        self.timer.stop()
        p = self.prefs()
        if not p.get("enabled", True) or not self.repo():
            return
        interval = min(max(1, int(p.get("interval_hours", 6))), 720) * 3600
        wait = retry_sec if retry_sec is not None else p.get("last_check", 0) + interval - time.time()
        self.timer.start(int(max(wait, STARTUP_DELAY_SEC) * 1000))

    # ---- network -----------------------------------------------------------
    def _get(self, url):
        if self._nam is None:
            self._nam = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", USER_AGENT)
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setTransferTimeout(TIMEOUT_MS)
        return self._nam.get(req)

    def check(self, manual=False):
        repo = self.repo()
        if not repo:
            if manual:
                self.check_failed.emit("업데이트 저장소가 아직 설정되지 않았어요.")
            return
        if self._check_reply:
            return
        self._check_reply = reply = self._get(f"{API}/repos/{repo}/releases/latest")
        reply.finished.connect(lambda: self._on_checked(reply, manual))

    def _on_checked(self, reply, manual):
        self._check_reply = None
        reply.deleteLater()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if reply.error() != QNetworkReply.NoError and status != 404:
            self.reschedule(RETRY_AFTER_FAIL_SEC)
            if manual:
                self.check_failed.emit("업데이트 정보를 가져오지 못했어요.\n인터넷 연결을 확인해 주세요.")
            return
        self.prefs()["last_check"] = time.time()
        config.save(self.settings)
        self.reschedule()
        release = None
        if status != 404:
            try:
                release = pick_release(json.loads(bytes(reply.readAll()).decode("utf-8")))
            except (ValueError, AttributeError, TypeError):
                release = None
        if release and semver.is_newer(release["version"], self.version):
            self.update_available.emit(release)
        elif manual:
            self.no_update.emit()

    # ---- download ----------------------------------------------------------
    def download(self, release):
        self.cancel()
        self._release = release
        if release.get("sha_url"):
            reply = self._get(release["sha_url"])
            reply.finished.connect(lambda: self._on_checksum(reply))
        elif release.get("sha256"):
            self._start_download(release["sha256"])
        else:
            self.download_failed.emit("검증 정보(SHA256)가 없어 설치할 수 없어요.")

    def _on_checksum(self, reply):
        reply.deleteLater()
        text = bytes(reply.readAll()).decode("utf-8", "ignore") if reply.error() == QNetworkReply.NoError else ""
        m = re.search(r"\b[0-9a-fA-F]{64}\b", text)
        if m:
            self._start_download(m.group(0).lower())
        else:
            self.download_failed.emit("검증 정보(SHA256)를 받지 못했어요.\n잠시 후 다시 시도해 주세요.")

    def _start_download(self, expected):
        os.makedirs(download_dir(), exist_ok=True)
        self._expected = expected
        self._hash = QCryptographicHash(QCryptographicHash.Sha256)
        self._file = QFile(os.path.join(download_dir(), os.path.basename(self._release["file"])))
        if not self._file.open(QIODevice.WriteOnly | QIODevice.Truncate):
            self._file = None
            self.download_failed.emit("임시 폴더에 파일을 저장할 수 없어요.")
            return
        self._reply = reply = self._get(self._release["url"])
        reply.readyRead.connect(self._on_data)
        reply.downloadProgress.connect(lambda done, total: self.progress.emit(done, total))
        reply.finished.connect(self._on_downloaded)

    def _on_data(self):
        chunk = self._reply.readAll()
        if chunk.size():
            self._hash.addData(chunk)
            self._file.write(chunk)

    def _on_downloaded(self):
        if self._reply is None:
            return
        self._on_data()
        reply, self._reply = self._reply, None
        reply.deleteLater()
        path = os.path.normpath(self._file.fileName())
        self._file.close()
        self._file = None
        ok = reply.error() == QNetworkReply.NoError
        if not ok:
            QFile.remove(path)
            if reply.error() != QNetworkReply.OperationCanceledError:
                self.download_failed.emit("다운로드에 실패했어요.\n인터넷 연결을 확인해 주세요.")
            return
        actual = bytes(self._hash.result().toHex()).decode()
        if actual != self._expected:
            QFile.remove(path)
            self.download_failed.emit("다운로드한 파일 검증에 실패했어요.\n안전을 위해 설치하지 않았어요.")
            return
        self.downloaded.emit(path)

    def cancel(self):
        if self._reply:
            self._reply.abort()

    @staticmethod
    def install(path):
        """Start the installer as a separate process; the caller must quit right after."""
        return QProcess.startDetached(path, INSTALLER_ARGS)
