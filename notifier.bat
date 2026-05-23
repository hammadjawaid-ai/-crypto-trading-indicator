@echo off
title Crypto Indicator - Desktop Alert Notifier
cd /d "%~dp0"

echo ===============================================================
echo    CRYPTO TRADING INDICATOR  -  desktop alert notifier
echo ===============================================================
echo.
echo  Fires real Windows notifications for new high-confidence
echo  setups and volume surges - no browser needed.
echo.
echo  Default : 1h + 15m timeframes, scans every 5 minutes.
echo  Custom  : notifier.bat 4h 10           (just 4h, every 10 min)
echo            notifier.bat 1h,15m,4h 5     (three timeframes, every 5 min)
echo.
echo  Keep this window OPEN. Close it (or press Ctrl+C) to stop alerts.
echo ===============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo  ERROR: the .venv folder was not found in this directory.
    echo  This file must sit in the project folder next to notifier.py.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" notifier.py %*

echo.
echo  The notifier has stopped.
pause
