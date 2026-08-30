@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "scripts\run_eval.py" --phase legitimate-revision --count 10
pause
