@echo off
cd /d "%~dp0"
echo.
echo   Manufacturing Operation Database
echo   =================================
echo.
echo   Stopping the app...
echo.
docker compose down
echo.
echo   The app has been stopped.
echo.
pause
