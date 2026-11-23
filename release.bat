@echo off
chcp 65001 >nul
cd /d "%~dp0"
set VER=%1
if "%VER%"=="" set /p VER=새 버전 번호를 입력하세요 (예: 1.0.1 / 그대로 두려면 Enter): 
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install -q -r requirements.txt
.venv\Scripts\python tools\release.py %VER%
pause
