# PyInstaller spec: python -m PyInstaller pet.spec --noconfirm  ->  dist/DesktopPet/DesktopPet.exe
import os

DROP_BINARIES = (
    "opengl32sw", "d3dcompiler", "qt6pdf", "qt6qml", "qt6quick", "qt6opengl",
    "qt6svg", "qt6virtualkeyboard", "qt6dbus",
    "plugins/imageformats", "plugins/iconengines", "plugins/generic", "plugins/networkinformation",
    "plugins/platforminputcontexts",
    "platforms/qminimal", "platforms/qoffscreen", "platforms/qdirect2d",
    # HTTPS uses Windows' built-in Schannel (tls/qschannelbackend.dll); no OpenSSL needed
    "qopensslbackend", "qcertonlybackend", "libssl", "libcrypto",
)

a = Analysis(
    ["pet/main.py"],
    pathex=["pet"],
    datas=[("assets/characters", "characters"), ("version.json", ".")],
    hiddenimports=["logging"],  # needed by PySide6's shibokensupport
    excludes=[
        "tkinter", "unittest", "pydoc", "doctest", "email", "http", "xml", "xmlrpc", "sqlite3",
        "multiprocessing", "asyncio", "ssl", "_ssl", "lzma", "bz2", "ctypes.test", "distutils",
        "hashlib", "_hashlib", "decimal", "_decimal", "socket", "_socket", "select", "pyexpat",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL",
        "PySide6.QtSvg", "PySide6.QtPdf", "PySide6.QtDBus",
    ],
)


def keep(entry):
    name = entry[0].replace(os.sep, "/").lower()
    return not any(k in name for k in DROP_BINARIES)


a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if "translations" not in d[0].replace(os.sep, "/").lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="DesktopPet",
    icon="assets/app.ico",
    console=os.environ.get("PET_CONSOLE") == "1",
    upx=False,
    strip=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="DesktopPet", upx=False, strip=False)
