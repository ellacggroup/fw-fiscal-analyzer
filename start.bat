@echo off
cd /d "%~dp0"

echo.
echo ===================================================
echo   Fort Worth Fiscal Impact Analyzer
echo ===================================================
echo.

:: ── Check setup was completed ────────────────────────
if not exist "backend\venv\Scripts\python.exe" (
    echo  The app is not set up yet.
    echo  Please double-click setup.bat first.
    echo.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo  The webpage interface is not set up yet.
    echo  Please double-click setup.bat first.
    echo.
    pause
    exit /b 1
)

:: ── Kill any stale server on port 8000 ───────────────
echo  Clearing any previous instances...
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue; if($c){Stop-Process -Id $c[0].OwningProcess -Force}" >nul 2>&1
timeout /t 2 /nobreak >nul

:: ── Clear Python bytecode cache ──────────────────────
for /r "backend" %%d in (__pycache__) do (
    if exist "%%d" rd /s /q "%%d" >nul 2>&1
)

:: ── Start backend ─────────────────────────────────────
echo  Starting the backend...
start "FW Fiscal - Backend" cmd /k "cd /d "%~dp0backend" && venv\Scripts\activate && uvicorn main:app --reload --port 8000"

echo  Waiting for backend to be ready...
timeout /t 7 /nobreak >nul

:: ── Start frontend ────────────────────────────────────
echo  Starting the webpage interface...
start "FW Fiscal - Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

timeout /t 4 /nobreak >nul

:: ── Open browser ──────────────────────────────────────
echo.
echo ===================================================
echo   App is running!  Open: http://localhost:5173
echo   Keep both black windows open while using the app.
echo ===================================================
echo.

start "" "http://localhost:5173"
pause
