@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto erro_pasta

echo ===========================================
echo   Instalacao do Sistema de Rotogramas
echo ===========================================
echo.
echo Mantenha a internet conectada durante a instalacao.
echo Os cadastros existentes serao preservados.
echo.

if not exist "app.py" goto erro_arquivos
if not exist "requirements.txt" goto erro_arquivos

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto usar_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto usar_python
goto erro_python

:usar_py
set "PY_CMD=py -3"
goto preparar

:usar_python
set "PY_CMD=python"

:preparar
echo [1/3] Preparando o ambiente Python...
%PY_CMD% -m venv ".venv"
if errorlevel 1 goto erro_ambiente

echo.
echo [2/3] Instalando as dependencias...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 goto erro_dependencias

echo.
echo [3/3] Verificando a instalacao...
".venv\Scripts\python.exe" -c "import flask, flask_sqlalchemy, pymysql, dotenv, alembic, tzdata, waitress"
if errorlevel 1 goto erro_dependencias

echo.
echo Instalacao concluida com sucesso!
echo Para abrir o sistema, execute iniciar.bat.
echo Depois acesse http://127.0.0.1:5000 no navegador.
echo.
pause
exit /b 0

:erro_python
echo.
echo ERRO: Python 3.10 ou superior nao foi encontrado.
echo Confirme se Python esta instalado e disponivel no terminal.
goto falha

:erro_arquivos
echo.
echo ERRO: app.py ou requirements.txt nao foi encontrado.
echo Extraia toda a pasta do ZIP antes de executar este arquivo.
goto falha

:erro_ambiente
echo.
echo ERRO: Nao foi possivel preparar o ambiente Python.
echo Confira a mensagem acima e a permissao de escrita nesta pasta.
goto falha

:erro_dependencias
echo.
echo ERRO: Nao foi possivel instalar ou verificar as dependencias.
echo Confira a conexao com a internet e a mensagem acima.
echo Depois execute instalar.bat novamente.
goto falha

:erro_pasta
echo ERRO: Nao foi possivel acessar a pasta do sistema.

:falha
echo.
echo A instalacao nao foi concluida.
pause
exit /b 1