@echo off
setlocal
title MES Subtitle Assistant

cd /d "%~dp0"

powershell -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:15000/' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
if not errorlevel 1 (
    echo MES Subtitle Assistant is already running.
    start "" "http://127.0.0.1:15000"
    exit /b 0
)

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo Python 3 was not found.
    echo Install Python 3.10 or later, then run this file again.
    echo You can send this message to Codex for installation help.
    pause
    exit /b 1
)

set "HAS_API_KEY="
set "DEEPSEEK_KEY="
if exist "..\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("..\.env") do (
        if /I "%%A"=="DeepSeek_Key" if not "%%B"=="" set "HAS_API_KEY=1"
    )
)

if not defined HAS_API_KEY (
    echo.
    echo First start: a DeepSeek API Key is required.
    powershell -NoProfile -Command "$key = Read-Host 'Paste your DeepSeek API Key, then press Enter' -AsSecureString; $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($key); try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr); if ([string]::IsNullOrWhiteSpace($plain)) { exit 1 }; @('# Local configuration. Do not upload this file to GitHub.', ('DeepSeek_Key=' + $plain), '', 'MES_ENABLE_ENGLISH_REFLOW=1') | Set-Content -LiteralPath '..\.env' -Encoding utf8 } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }"
    if errorlevel 1 (
        echo No API Key was entered. The application cannot start.
        pause
        exit /b 1
    )
    echo The local API Key configuration has been saved.
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local runtime environment. Please wait...
    call %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo Python environment creation failed. Send this window content to Codex.
        pause
        exit /b 1
    )
)

call .venv\Scripts\python.exe -m pip install -r app\requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. Check the network and try again, or send this window content to Codex.
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in ("..\.env") do (
    if /I "%%A"=="DeepSeek_Key" set "DeepSeek_Key=%%B"
    if /I "%%A"=="MES_ENABLE_ENGLISH_REFLOW" set "MES_ENABLE_ENGLISH_REFLOW=%%B"
)

echo.
echo MES Subtitle Assistant is starting...
echo The browser will open: http://127.0.0.1:15000
echo.

start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:15000'"
cd app
call ..\.venv\Scripts\python.exe main.py
