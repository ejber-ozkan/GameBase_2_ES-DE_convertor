@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ==================================================
echo   GameBase to ES-DE Metadata Converter (Windows)
echo ==================================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on your system.
    echo Please install Python 3.x from https://www.python.org/
    echo and ensure you check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Set up virtual environment
if not exist venv (
    echo [INFO] Python virtual environment 'venv' not found. Creating one...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    
    echo [INFO] Virtual environment created.
    echo [INFO] Installing required dependencies (access-parser)...
    .\venv\Scripts\pip.exe install access-parser
    if errorlevel 1 (
        echo [ERROR] Failed to install access-parser library.
        pause
        exit /b 1
    )
    echo [INFO] Dependencies installed successfully.
    echo.
)

:: 3. Run the converter script
echo [INFO] Running converter script...
.\venv\Scripts\python.exe convert_gamebase.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Conversion failed. Please check the error messages above.
    echo.
    pause
    exit /b 1
)

echo.
echo [INFO] Process completed successfully!
echo.
pause
