@echo off
chcp 65001 > nul
echo ========================================
echo    Synology Chat Bot Launcher
echo ========================================
echo.

REM Проверяем наличие Python
python --version > nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found! Please install Python 3.8+
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Checking Python version...
python -c "import sys; print('Python version:', sys.version)"

echo.
echo Installing dependencies...
call pip install -r requirements.txt

echo.
echo Starting Synology Chat Bot...
echo Bot will be available at: http://localhost:5000
echo Press Ctrl+C to stop the bot
echo.

python bot.py

pause