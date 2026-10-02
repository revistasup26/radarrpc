@echo off
chcp 65001 >nul
title Radar RPC
cd /d "%~dp0backend"

set RADAR_PORT=8922

echo ============================================================
echo   RADAR RPC - Revista Panamericana de Comunicacion
echo   PWA:    http://localhost:%RADAR_PORT%/app/
echo   Widget: http://localhost:%RADAR_PORT%/widget
echo ============================================================
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Entorno virtual no encontrado. Instala primero:
    echo   uv venv .venv
    echo   uv pip install --python .venv fastapi "uvicorn[standard]" apscheduler httpx
    pause
    exit /b 1
)

echo  [1] Solo arrancar el servidor (datos ya cosechados)
echo  [2] Cosechar 30 dias y arrancar
echo  [3] Cosecha completa 1 anio y arrancar
echo.
set /p OPCION="Elige una opcion (1/2/3): "

if "%OPCION%"=="2" .venv\Scripts\python.exe -m radar.harvester.cli --days 30 --max-articles 800
if "%OPCION%"=="3" .venv\Scripts\python.exe -m radar.harvester.cli --days 365 --max-articles 2500

start "" "http://localhost:%RADAR_PORT%/app/"
echo Arrancando servidor (IPv4 + IPv6)... cierra la ventana con Ctrl+C.
.venv\Scripts\python.exe run_server.py
pause