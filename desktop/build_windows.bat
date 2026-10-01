@echo off
REM Build MaintDB.exe (unsigned) on Windows with Python 3.12 installed.
REM   desktop\build_windows.bat
REM Output: dist\MaintDB\MaintDB.exe  (the whole dist\MaintDB folder is the app)
setlocal
cd /d "%~dp0\.."
set "PY=python"

echo 1/4  Installing build deps (app deps + pyinstaller + pywebview)...
%PY% -m pip install -r requirements.txt
%PY% -m pip install pyinstaller pywebview

echo 2/4  Fetching relocatable PostgreSQL binaries...
%PY% desktop\fetch_postgres.py windows

echo 3/4  Building MaintDB.exe (this takes a few minutes)...
%PY% -m PyInstaller desktop\maintdb.spec --noconfirm --clean

echo 4/4  Done. The app is the folder: dist\MaintDB  (run MaintDB.exe inside it)
echo Unsigned build: Windows SmartScreen shows a one-time "More info -> Run anyway" prompt.
endlocal
