"""Build a release: EXE -> installer -> SHA256 file -> (optional) upload to GitHub Releases.

usage: python tools/release.py [new_version]      e.g. python tools/release.py 1.1.0
Run through release.bat; see README.md.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pet"))
from app import semver  # noqa: E402

VERSION_FILE = os.path.join(ROOT, "version.json")
NOTES_FILE = os.path.join(ROOT, "release_notes.md")
RELEASE_DIR = os.path.join(ROOT, "release")


def fail(msg):
    print("\n[실패] " + msg)
    sys.exit(1)


def run(cmd):
    print("\n> " + " ".join(cmd))
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        fail("위 명령이 실패했어요. 오류 내용을 Cursor에 그대로 붙여넣어 주세요.")


def find_iscc():
    candidates = [shutil.which("ISCC")] + glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup*\ISCC.exe")) \
        + glob.glob(r"C:\Program Files*\Inno Setup*\ISCC.exe")
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def main():
    with open(VERSION_FILE, encoding="utf-8-sig") as f:
        info = json.load(f)
    if len(sys.argv) > 1:
        new = sys.argv[1].lstrip("vV")
        if not semver.parse(new):
            fail(f"'{new}' 은(는) 올바른 버전이 아니에요. 예: 1.0.1")
        if not semver.is_newer(new, info["version"]):
            print(f"[주의] 새 버전 {new} 이(가) 현재 버전 {info['version']} 보다 높지 않아요. "
                  "사용자에게 업데이트 알림이 뜨지 않습니다.")
        info["version"] = new
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
            f.write("\n")
    version = info["version"]
    print(f"=== DesktopPet {version} 배포 파일 만들기 ===")

    iscc = find_iscc()
    if not iscc:
        fail("Inno Setup이 없어요. README.md의 '처음 한 번만 준비' 부분을 따라 설치해 주세요.")

    run([sys.executable, "-m", "PyInstaller", "pet.spec", "--noconfirm", "--log-level", "WARN"])
    run([iscc, "/Q", f"/DAppVersion={version}", os.path.join("installer", "DesktopPet.iss")])

    setup = os.path.join(RELEASE_DIR, f"DesktopPet-Setup-{version}.exe")
    if not os.path.isfile(setup):
        fail("설치 파일이 만들어지지 않았어요.")
    digest = hashlib.sha256(open(setup, "rb").read()).hexdigest()
    sha_file = setup + ".sha256"
    with open(sha_file, "w", encoding="ascii") as f:
        f.write(f"{digest} *{os.path.basename(setup)}\n")
    notes = open(NOTES_FILE, encoding="utf-8-sig").read().strip() if os.path.isfile(NOTES_FILE) else ""

    print("\n=== 완료 ===")
    print(f"설치 파일 : {setup} ({os.path.getsize(setup) / 1048576:.1f} MB)")
    print(f"체크섬    : {sha_file}")
    print(f"업데이트 설명(release_notes.md):\n{notes or '(비어 있음)'}")

    repo = info.get("repo", "")
    if repo and shutil.which("gh"):
        answer = input(f"\nGitHub({repo})에 v{version} 으로 바로 올릴까요? (y/n): ").strip().lower()
        if answer == "y":
            run(["gh", "release", "create", f"v{version}", setup, sha_file, "--repo", repo,
                 "--title", f"v{version}", "--notes-file", NOTES_FILE])
            print("\nGitHub 업로드 완료! 사용자 프로그램이 다음 확인 때 업데이트를 알려줘요.")
            return
    print("\nGitHub 웹사이트에서 올리는 방법은 README.md의 'GitHub에 올리기'를 보세요.")
    print(f"  태그: v{version}   첨부 파일 2개: {os.path.basename(setup)}, {os.path.basename(sha_file)}")


if __name__ == "__main__":
    main()
