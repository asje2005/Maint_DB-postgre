@echo off
REM Double-click to build the MaintDB desktop app (Windows). No commands to type.
title Build the MaintDB Desktop App
cls
echo.
echo   Build the MaintDB Desktop App (Windows)
echo   =======================================
echo.
echo   This makes a double-clickable app (dist\MaintDB\MaintDB.exe) that runs with
echo   nothing else installed. It takes a few minutes the first time.
echo.

cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python isn't installed.
    echo   Install Python 3.12 from https://www.python.org/downloads/
    echo   ^(tick "Add python.exe to PATH" during setup^), then double-click this again.
    echo.
    pause
    exit /b 1
)

echo   Building...
echo.
call desktop\build_windows.bat
if %errorlevel% neq 0 (
    echo.
    echo   The build hit a problem. The messages above explain what happened.
    echo.
    pause
    exit /b 1
)

echo.
echo   Done!  Your app is the folder:  dist\MaintDB
echo   Run MaintDB.exe inside it. First launch: "More info" -^> "Run anyway" (one time).
echo   Opening the folder now...
start "" "dist\MaintDB"
echo.
pause
