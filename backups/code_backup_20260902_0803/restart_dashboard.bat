@echo off
echo Restarting Flask dashboard...

REM Kill all Python processes listening on port 5001
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "5001.*LISTENING"') do (
    taskkill /PID %%a /F 2>nul
    echo Killed PID %%a
)

timeout /t 3 /nobreak

REM Start Flask
cd /d d:\prospection-machine
python dashboard\app.py

pause
