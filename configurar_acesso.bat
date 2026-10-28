@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute instalar.bat primeiro.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m flask --app app preparar-acesso
if errorlevel 1 echo Nao foi possivel concluir a configuracao.
pause
