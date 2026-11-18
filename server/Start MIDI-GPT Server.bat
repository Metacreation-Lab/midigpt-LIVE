@echo off
REM Double-click to start the MIDI-GPT server on Windows: http://127.0.0.1:3456 by default.
REM Keep this window open while you use MIDI-GPT in Live; Ctrl+C stops the server.
REM
REM The installer (install.ps1) sets up the server's Python environment in %APPDATA%\MIDI-GPT\server\.venv (or the
REM folder in MIDIGPT_SERVER_DIR, or the server_dir it recorded in live.json), and writes models.yaml (the models to
REM load) and server.conf (PORT=, and MODEL= for when there is no models.yaml) next to it. Arguments go to midigpt-http
REM after the defaults, so they override them, e.g. --host 0.0.0.0 to reach the server from other computers;
REM --pretrained NAME serves just that model, ignoring models.yaml. The device (GPU or CPU) is set in models.yaml;
REM without it, --device auto: the NVIDIA GPU when PyTorch has CUDA, else the CPU.
setlocal

set "SERVER_DIR=%MIDIGPT_SERVER_DIR%"
if not defined SERVER_DIR if exist "%APPDATA%\MIDI-GPT\live.json" (
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "(Get-Content -Raw $env:APPDATA\MIDI-GPT\live.json | ConvertFrom-Json).server_dir"`) do set "SERVER_DIR=%%d"
)
if not defined SERVER_DIR set "SERVER_DIR=%APPDATA%\MIDI-GPT\server"
set "VENV=%SERVER_DIR%\.venv"
set "MODELS=%SERVER_DIR%\models.yaml"
set "MODEL=yellow_medium"
set "PORT=3456"
if exist "%SERVER_DIR%\server.conf" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%SERVER_DIR%\server.conf") do set "%%a=%%b"
)

if not exist "%VENV%\Scripts\midigpt-http.exe" (
    echo The MIDI-GPT server isn't installed ^(no environment in %VENV%^).
    echo Install it from PowerShell with:
    echo   ^& ^([scriptblock]::Create^(^(irm https://metacreation.net/midigpt-LIVE/bootstrap.ps1^)^)^) -Server
    echo.
    pause
    exit /b 1
)

REM what to load: models.yaml (config), else MODEL (single); a model in the arguments wins over both (own)
set "MODE=single"
if exist "%MODELS%" set "MODE=config"
set "ARGS=x%*"
if not "%ARGS:--pretrained=%"=="%ARGS%" set "MODE=single"
if not "%ARGS:--ckpt=%"=="%ARGS%" set "MODE=own"
if not "%ARGS:--config=%"=="%ARGS%" set "MODE=own"

REM a mistake in models.yaml, said in plain words instead of the server's traceback
if "%MODE%"=="config" if exist "%~dp0check_models.py" (
    "%VENV%\Scripts\python.exe" "%~dp0check_models.py" "%MODELS%"
    if errorlevel 1 (
        echo.
        pause
        exit /b 1
    )
)

echo.
if "%MODE%"=="config" (
    echo   MIDI-GPT server on http://127.0.0.1:%PORT% ^(models from models.yaml^)
    echo   Models are set in %MODELS%
)
if "%MODE%"=="single" echo   MIDI-GPT server on http://127.0.0.1:%PORT% (model %MODEL%)
if "%MODE%"=="own" echo   MIDI-GPT server on http://127.0.0.1:%PORT%
echo   Keep this window open while you use MIDI-GPT in Live. Press Ctrl+C to stop the server.
if "%MODE%"=="config" if not "%ARGS:--device=%"=="%ARGS%" echo   --device has no effect with models.yaml: set device: in that file instead.
echo.

REM a failed generation's request is saved here, to attach to a bug report (docs/reporting-bugs.md)
if not defined MIDIGPT_FAILED_REQUESTS_LOG set "MIDIGPT_FAILED_REQUESTS_LOG=%SERVER_DIR%\failed_requests.jsonl"
if "%MODE%"=="config" "%VENV%\Scripts\midigpt-http.exe" --config "%MODELS%" --host 127.0.0.1 --port %PORT% %*
if "%MODE%"=="single" "%VENV%\Scripts\midigpt-http.exe" --pretrained %MODEL% --device auto --host 127.0.0.1 --port %PORT% %*
if "%MODE%"=="own" "%VENV%\Scripts\midigpt-http.exe" --device auto --host 127.0.0.1 --port %PORT% %*

if errorlevel 1 (
    echo.
    echo The server stopped.
    echo If the message above mentions a gated repo, 401 or 403: accept the license at
    echo https://huggingface.co/Metacreation/MIDI-GPT, then save a token with:
    echo   "%VENV%\Scripts\hf.exe" auth login
    if "%MODE%"=="config" echo If it mentions models.yaml or a model entry, check that file: %MODELS%
    echo.
    pause
)
endlocal
