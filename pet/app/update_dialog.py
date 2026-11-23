from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout,
)

STYLE = """
QDialog { background: #FFF8EC; }
QLabel { color: #5A3A20; font-family: 'Malgun Gothic'; font-size: 10pt; }
QLabel#title { color: #7A4A22; font-size: 13pt; font-weight: bold; }
QLabel#error { color: #C0392B; }
QTextBrowser { background: #FFFDF7; border: 2px solid #E8C9A0; border-radius: 10px; padding: 4px;
               color: #5A3A20; font-family: 'Malgun Gothic'; font-size: 10pt; }
QPushButton { border: none; border-radius: 13px; padding: 7px 18px; font-family: 'Malgun Gothic';
              font-size: 10pt; font-weight: bold; }
QPushButton#primary { background: #FF8A65; color: white; }
QPushButton#primary:hover { background: #FF7043; }
QPushButton#secondary { background: #F3E3CC; color: #7A4A22; }
QPushButton#secondary:hover { background: #EBD3B3; }
QProgressBar { border: 2px solid #E8C9A0; border-radius: 9px; background: #FFFDF7; height: 16px;
               text-align: center; color: #7A4A22; font-weight: bold; }
QProgressBar::chunk { background: #FFB74D; border-radius: 7px; }
"""


class UpdateDialog(QDialog):
    """New-version popup; the same window shows download progress after '지금 업데이트'."""

    def __init__(self, updater, release, current_version, icon):
        super().__init__(None, Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("업데이트")
        self.setWindowIcon(icon)
        self.setStyleSheet(STYLE)
        self.setFixedWidth(360)
        self.updater = updater
        self.release = release
        self.installing = False
        self.downloading = False

        pic = QLabel()
        pic.setPixmap(icon.pixmap(44, 44))
        title = QLabel("새 업데이트가 있어요!")
        title.setObjectName("title")
        header = QHBoxLayout()
        header.addWidget(pic)
        header.addWidget(title, 1)

        self.info = QLabel(f"새로운 버전 {release['version']}이 출시되었습니다.\n(현재 버전 {current_version})")
        self.notes = QTextBrowser()
        self.notes.setOpenLinks(False)
        self.notes.setMarkdown("**이번 업데이트:**\n\n" + (release["notes"] or "- 자잘한 개선"))
        self.notes.setMaximumHeight(150)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.status.hide()
        self.bar.hide()

        self.now_btn = QPushButton("지금 업데이트")
        self.now_btn.setObjectName("primary")
        self.later_btn = QPushButton("나중에")
        self.later_btn.setObjectName("secondary")
        self.now_btn.clicked.connect(self.start_update)
        self.later_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.now_btn)
        buttons.addWidget(self.later_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        root.addLayout(header)
        root.addWidget(self.info)
        root.addWidget(self.notes)
        root.addWidget(self.status)
        root.addWidget(self.bar)
        root.addLayout(buttons)

        updater.progress.connect(self.on_progress)
        updater.downloaded.connect(self.on_downloaded)
        updater.download_failed.connect(self.on_failed)

    def start_update(self):
        self.downloading = True
        self.now_btn.hide()
        self.later_btn.setText("취소")
        self.status.setObjectName("")
        self.status.setStyleSheet("")
        self.status.setText("업데이트 다운로드 중...")
        self.status.show()
        self.bar.setValue(0)
        self.bar.show()
        self.updater.download(self.release)

    def on_progress(self, done, total):
        if total > 0:
            self.bar.setValue(int(done * 100 / total))
            self.status.setText(f"업데이트 다운로드 중... {done / 1048576:.1f} / {total / 1048576:.1f} MB")

    def on_downloaded(self, path):
        self.downloading = False
        self.bar.setValue(100)
        self.later_btn.hide()
        self.status.setText("다운로드 완료! 파일 확인 완료.\n설치 준비 중... 잠시 후 프로그램이 다시 시작돼요.")
        QTimer.singleShot(1200, lambda: self._install(path))

    def _install(self, path):
        if self.updater.install(path):
            self.installing = True
            self.accept()
        else:
            self.on_failed("설치 프로그램을 실행하지 못했어요.")

    def on_failed(self, message):
        self.downloading = False
        self.bar.hide()
        self.status.setStyleSheet("color: #C0392B;")
        self.status.setText(message + "\n지금 버전은 그대로 사용할 수 있어요.")
        self.status.show()
        self.later_btn.setText("닫기")
        self.later_btn.show()

    def done(self, result):
        if self.downloading:
            self.downloading = False
            self.updater.cancel()
        super().done(result)
