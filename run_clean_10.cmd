@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "scripts\run_eval.py" --phase clean --count 10
pause
