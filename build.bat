@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install -q -r requirements.txt
.venv\Scripts\python -m PyInstaller pet.spec --noconfirm
echo.
echo Built: dist\DesktopPet\DesktopPet.exe
pause
