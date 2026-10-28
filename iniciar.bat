@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute instalar.bat antes de iniciar o sistema.
 pause
 exit /b 1
)
"%~dp0.venv\Scripts\python.exe" servidor.py
pause
