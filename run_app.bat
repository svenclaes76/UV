@echo off
git pull
cd /d "%~dp0"
".venv\Scripts\python.exe" run_app.py
pause
