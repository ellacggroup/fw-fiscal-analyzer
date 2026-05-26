@echo off
cd /d "%~dp0"

echo.
echo ===================================================
echo   Fort Worth Fiscal Impact Analyzer - Setup
echo ===================================================
echo.

:: ── Check Python ────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python was not found on this computer.
    echo.
    echo  Please install Python by doing these steps:
    echo    1. Open your browser and go to: https://www.python.org/downloads/
    echo    2. Click the big yellow "Download Python" button
    echo    3. Run the installer
    echo    4. IMPORTANT: on the first screen, check the box that says
    echo       "Add Python to PATH"  before clicking Install Now
    echo    5. After it finishes, close this window and run setup.bat again
    echo.
    pause
    exit /b 1
)

echo  Python found:
python --version
echo.

:: ── Check Node.js ────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Node.js was not found on this computer.
    echo.
    echo  Please install Node.js by doing these steps:
    echo    1. Open your browser and go to: https://nodejs.org/
    echo    2. Click the "LTS" download button (the left one)
    echo    3. Run the installer, click Next through everything
    echo    4. After it finishes, close this window and run setup.bat again
    echo.
    pause
    exit /b 1
)

echo  Node.js found:
node --version
echo.

:: ── Backend setup ────────────────────────────────────
echo  [1/2] Setting up the Python backend...
echo        (This may take 2-3 minutes, please wait)
echo.

cd backend

if not exist venv (
    python -m venv venv
    if errorlevel 1 (
        echo  ERROR: Could not create Python environment.
        echo  Try running this window as Administrator and try again.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate

pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo  ERROR: Could not install Python packages.
    echo  Make sure you are connected to the internet and try again.
    pause
    exit /b 1
)

cd ..

echo  Backend ready!
echo.

:: ── Frontend setup ───────────────────────────────────
echo  [2/2] Setting up the webpage interface...
echo        (This may take 1-2 minutes, please wait)
echo.

cd frontend

call npm install --silent
if errorlevel 1 (
    echo.
    echo  ERROR: Could not install webpage packages.
    echo  Make sure you are connected to the internet and try again.
    pause
    exit /b 1
)

cd ..

echo.
echo ===================================================
echo   Setup complete!
echo.
echo   To start the application, double-click:
echo      start.bat
echo.
echo   Then open your browser to:
echo      http://localhost:5173
echo ===================================================
echo.
pause
