@echo off
REM Double-click to start the MIDI-GPT server on Windows: http://127.0.0.1:3456 by default.
REM Keep this window open while you use MIDI-GPT in Live; Ctrl+C stops the server.
REM
REM The server's Python environment is %APPDATA%\MIDI-GPT\server\.venv (or the folder in MIDIGPT_SERVER_DIR), and
REM server.conf next to it may set MODEL= and PORT=. Arguments go to midigpt-http after the defaults, so they override
REM them, e.g. --host 0.0.0.0 to reach the server from other computers. --device auto: the GPU when there is one.
setlocal

if defined MIDIGPT_SERVER_DIR (set "SERVER_DIR=%MIDIGPT_SERVER_DIR%") else (set "SERVER_DIR=%APPDATA%\MIDI-GPT\server")
set "VENV=%SERVER_DIR%\.venv"
set "MODEL=yellow_medium"
set "PORT=3456"
if exist "%SERVER_DIR%\server.conf" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%SERVER_DIR%\server.conf") do set "%%a=%%b"
)

if not exist "%VENV%\Scripts\midigpt-http.exe" (
    echo The MIDI-GPT server isn't installed ^(no environment in %VENV%^).
    echo Set it up with Python 3.10-3.14:
    echo   py -3.12 -m venv "%VENV%"
    echo   "%VENV%\Scripts\pip" install "midigpt[http,inference]==0.4.0"
    echo   "%VENV%\Scripts\hf" auth login
    echo.
    pause
    exit /b 1
)

echo.
echo   MIDI-GPT server on http://127.0.0.1:%PORT% (model %MODEL%)
echo   Keep this window open while you use MIDI-GPT in Live. Press Ctrl+C to stop the server.
echo.

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
