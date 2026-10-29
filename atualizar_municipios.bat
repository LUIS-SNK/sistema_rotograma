@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute instalar.bat primeiro.
 pause
 exit /b 1
)
echo Atualizando municipios e divisas pela API publica do IBGE.
echo Se a consulta falhar, a base anterior sera preservada.
".venv\Scripts\python.exe" -m flask --app app atualizar-municipios
if errorlevel 1 (
 echo Nao foi possivel concluir. Verifique sua conexao e tente novamente.
 pause
 exit /b 1
)
echo Base municipal atualizada. Nenhum vinculo e criado automaticamente.
pause
