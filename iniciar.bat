@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute instalar.bat antes de iniciar o sistema.
 pause
 exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m flask --app app preparar-acesso
if errorlevel 1 (
 echo Nao foi possivel preparar o acesso. Confira a mensagem acima.
 pause
 exit /b 1
)
"%~dp0.venv\Scripts\python.exe" servidor.py
pause
