@echo off
REM Double-click to start the MIDI-GPT server on Windows: http://127.0.0.1:3456 by default.
REM Keep this window open while you use MIDI-GPT in Live; Ctrl+C stops the server.
REM
REM The installer (install.ps1) sets up the server's Python environment in %APPDATA%\MIDI-GPT\server\.venv (or the
REM folder in MIDIGPT_SERVER_DIR, or the server_dir it recorded in live.json), and writes server.conf next to it
REM (MODEL=, PORT=). Arguments go to midigpt-http after the defaults, so they override them, e.g. --host 0.0.0.0 to
REM reach the server from other computers. --device auto: the NVIDIA GPU when PyTorch has CUDA, else the CPU.
setlocal

set "SERVER_DIR=%MIDIGPT_SERVER_DIR%"
if not defined SERVER_DIR if exist "%APPDATA%\MIDI-GPT\live.json" (
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "(Get-Content -Raw $env:APPDATA\MIDI-GPT\live.json | ConvertFrom-Json).server_dir"`) do set "SERVER_DIR=%%d"
)
if not defined SERVER_DIR set "SERVER_DIR=%APPDATA%\MIDI-GPT\server"
set "VENV=%SERVER_DIR%\.venv"
set "MODEL=yellow_medium"
set "PORT=3456"
if exist "%SERVER_DIR%\server.conf" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%SERVER_DIR%\server.conf") do set "%%a=%%b"
)

if not exist "%VENV%\Scripts\midigpt-http.exe" (
    echo The MIDI-GPT server isn't installed ^(no environment in %VENV%^).
    echo Install it from PowerShell with:
    echo   ^& ^([scriptblock]::Create^(^(irm https://metacreation.net/midigpt-live/bootstrap.ps1^)^)^) -Server
    echo.
    pause
    exit /b 1
)

echo.
echo   MIDI-GPT server on http://127.0.0.1:%PORT% (model %MODEL%)
echo   Keep this window open while you use MIDI-GPT in Live. Press Ctrl+C to stop the server.
echo.

REM a failed generation's request is saved here, to attach to a bug report (docs/reporting-bugs.md)
if not defined MIDIGPT_FAILED_REQUESTS_LOG set "MIDIGPT_FAILED_REQUESTS_LOG=%SERVER_DIR%\failed_requests.jsonl"
"%VENV%\Scripts\midigpt-http.exe" --pretrained %MODEL% --device auto --host 127.0.0.1 --port %PORT% %*

if errorlevel 1 (
    echo.
    echo The server stopped.
    echo If the message above mentions a gated repo, 401 or 403: accept the license at
    echo https://huggingface.co/Metacreation/MIDI-GPT, then save a token with:
    echo   "%VENV%\Scripts\hf.exe" auth login
    echo.
    pause
)
endlocal
