@echo off
REM Radar RPC - tarea de cosecha para el Programador de tareas de Windows (VPS Windows).
REM Ejemplo de alta (cada 6 horas):
REM   schtasks /create /tn "RadarRPC Harvest" /tr "C:\radar\harvest.bat" /sc hourly /mo 6 /ru SYSTEM
cd /d "%~dp0backend"
set RADAR_DATA_DIR=%~dp0data
set RADAR_DB_PATH=%~dp0data\radar.db
.venv\Scripts\python.exe -m radar.harvester.cli --days 30 --max-articles 1200 >> "%~dp0data\harvest_cron.log" 2>&1
