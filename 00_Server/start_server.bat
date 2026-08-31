@echo off
setlocal
chcp 65001 >nul
title MES Subtitle Assistant

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or later, then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

if not exist "..\.env" (
    echo Missing ..\.env
    echo Copy ..\.env.example to ..\.env, then set DeepSeek_Key before starting the application.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install -r app\requirements.txt

for /f "usebackq tokens=1,* delims==" %%A in ("..\.env") do (
    if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
)

echo.
echo MES Subtitle Assistant is starting.
echo Open: http://localhost:15000
echo.

cd app
python main.py
