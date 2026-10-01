@echo off
setlocal
cls
echo.
echo   Manufacturing Operation Database
echo   =================================
echo.

:: Check if Docker CLI is available
where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo   Docker Desktop is not installed.
    echo.
    echo   Please download and install it from:
    echo   https://www.docker.com/products/docker-desktop
    echo.
    echo   After installing, run this script again.
    echo.
    start https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

:: Check if Docker daemon is running
docker info >nul 2>&1
if %errorlevel% equ 0 goto dockerready

:: Try to start Docker Desktop (check both install locations)
echo   Starting Docker Desktop...
if exist "%PROGRAMFILES%\Docker\Docker\Docker Desktop.exe" (
    start "" "%PROGRAMFILES%\Docker\Docker\Docker Desktop.exe"
) else if exist "%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe" (
    start "" "%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe"
) else (
    echo   Could not locate Docker Desktop. Please open it manually and try again.
    pause
    exit /b 1
)

echo   Waiting for Docker to be ready. This may take up to 30 seconds...
echo.

:dockerwait
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if %errorlevel% neq 0 goto dockerwait

:dockerready
echo   Docker is ready.
echo.

:: Move to the folder this script lives in
cd /d "%~dp0"

:: Start the app
echo   Starting the app...
echo.
docker compose up -d

if %errorlevel% neq 0 (
    echo.
    echo   Something went wrong. Please contact your administrator.
    pause
    exit /b 1
)

:: Wait until the app responds
echo.
echo   Waiting for the app to be ready...

:appwait
timeout /t 2 /nobreak >nul
curl -s http://localhost:8501 >nul 2>&1
if %errorlevel% neq 0 goto appwait

:: Open the browser
echo.
echo   All done! Opening the app in your browser.
echo.
echo   If it does not open, go to: http://localhost:8501
echo.
echo   To stop the app, double-click "Stop App".
echo.
start http://localhost:8501
pause
