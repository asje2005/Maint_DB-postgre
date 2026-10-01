@echo off
setlocal EnableDelayedExpansion
cls
echo.
echo   Manufacturing Operation Database - Installer
echo   =============================================
echo.

set "PROJECT_DIR=%~dp0"

:: ── Step 1: Check for Docker Desktop ────────────────────────────────────────
echo   Checking for Docker Desktop...

where docker >nul 2>&1
if %errorlevel% equ 0 (
    echo   Docker Desktop is already installed.
) else (
    echo.
    echo   Docker Desktop is not installed. It is required to run this app.
    echo.
    echo   Opening the Docker Desktop download page now.
    echo.
    echo   After installing Docker Desktop, run this installer again.
    echo.
    start https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

echo.

:: ── Step 2: Start Docker if not already running ─────────────────────────────
docker info >nul 2>&1
if %errorlevel% equ 0 goto dockerready

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

echo   Waiting for Docker to be ready...
echo.

:dockerwait
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if %errorlevel% neq 0 goto dockerwait

:dockerready
echo   Docker is ready.
echo.

:: ── Step 3: Create a Desktop shortcut ───────────────────────────────────────
echo   Creating a shortcut on your Desktop...

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Start Manufacturing App.lnk'); $s.TargetPath = '%PROJECT_DIR%Start App.bat'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.Description = 'Start the Manufacturing Operation Database'; $s.Save()"

if %errorlevel% equ 0 (
    echo   Shortcut created on your Desktop.
) else (
    echo   Could not create shortcut. You can still run Start App.bat directly.
)

echo.

:: ── Step 4: Build the app and load the database ─────────────────────────────
echo   Building the app and loading the database...
echo   This may take a few minutes. Please wait.
echo.

cd /d "%PROJECT_DIR%"
docker compose up --build -d

if %errorlevel% neq 0 (
    echo.
    echo   Something went wrong during setup. Please contact your administrator.
    pause
    exit /b 1
)

echo   Waiting for the database to finish loading...
set /a WAITED=0

:setupwait
timeout /t 3 /nobreak >nul
set /a WAITED+=3
curl -s http://localhost:8501 >nul 2>&1
if %errorlevel% equ 0 goto setupdone
if !WAITED! geq 180 (
    echo   Setup is taking too long. Please contact your administrator.
    docker compose down
    pause
    exit /b 1
)
goto setupwait

:setupdone
echo   Database loaded successfully.
echo.
echo   Stopping containers (your data is saved)...
docker compose down

echo.
echo   =============================================
echo   Installation complete!
echo.
echo   To start the app:
echo   Double-click "Start Manufacturing App" on your Desktop.
echo.
pause
