@echo off

cd /d "%~dp0"

if not defined WT_SESSION (
    wt -d . cmd.exe /k call "%~f0"
    exit /b
)

:restart
.venv\Scripts\python.exe bot.py

if %ERRORLEVEL%==42 goto restart

pause