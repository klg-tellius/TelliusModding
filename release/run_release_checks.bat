@echo off
rem Runs every release test on the extracted discs given as arguments; see App/tools/release_checks.py.
rem Example: release\run_release_checks.bat G:\ROM\por_work G:\ROM\rd_work --saves G:\ROM\SaveFile --full
setlocal
cd /d "%~dp0..\App"
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
"%PY%" -m tools.release_checks %*
exit /b %ERRORLEVEL%
