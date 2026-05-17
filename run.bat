@echo off
title Crypto Trading Indicator
cd /d "%~dp0"

echo ===============================================================
echo    CRYPTO TRADING INDICATOR  -  local dashboard launcher
echo ===============================================================
echo.
echo  Project folder : %CD%
echo  Live cloud app : https://lzvswzxrr2dpnkhmckncuk.streamlit.app/
echo  GitHub repo    : github.com/hammadjawaid-ai/-crypto-trading-indicator
echo.
echo  Tabs: Market Scanner . Breakout Radar . Coin Analysis .
echo        News and Sentiment . Decision Mode
echo.
echo  Starting the app - it will open in your browser at:
echo        http://localhost:8501
echo.
echo  Keep this window OPEN while you use the app.
echo  Close this window (or press Ctrl+C) to stop it.
echo ===============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo  ERROR: the .venv folder was not found in this directory.
    echo  This file must sit in the project folder next to app.py.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run app.py

echo.
echo  The app has stopped.
pause
