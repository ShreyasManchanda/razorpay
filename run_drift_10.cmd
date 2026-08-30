@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "scripts\run_eval.py" --phase gradual-drift --count 10
pause
