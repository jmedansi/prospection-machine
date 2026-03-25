@echo off
setlocal
cd /d "%~dp0"

echo.
echo  [1] Lancer la Prospection Machine (Dashboard)
echo  [2] Eteindre la Prospection Machine (Stopper tout)
echo  [3] Quitter
echo.

set /p choice="Votre choix : "

if "%choice%"=="1" goto start_app
if "%choice%"=="2" goto stop_app
if "%choice%"=="3" exit
goto end

:start_app
echo.
echo [+] Lancement du Dashboard sur http://127.0.0.1:5001/ ...
echo [^!] Ne fermez pas cette fenetre pendant l'utilisation.
echo.
start /b python dashboard\app.py
timeout /t 3 >nul
start http://127.0.0.1:5001/
goto end

:stop_app
echo.
echo [-] Arret de tous les processus Python en cours...
taskkill /F /IM python.exe /T >nul 2>&1
echo [OK] Machine eteinte.
echo.
pause
goto end

:end
