@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute instalar.bat antes de atualizar o banco.
 pause
 exit /b 1
)
echo Feche o servidor e faca backup da pasta instance antes de prosseguir.
pause
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto falha
".venv\Scripts\python.exe" -m flask --app app atualizar-banco
if errorlevel 1 goto falha
echo Atualizacao concluida. Execute iniciar.bat.
pause
exit /b 0
:falha
echo A atualizacao falhou. Confira a mensagem acima.
pause
exit /b 1
