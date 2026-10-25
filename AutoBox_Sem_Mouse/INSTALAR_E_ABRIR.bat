@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
    echo Python nao encontrado. Instale Python 3.11 ou mais recente em python.org
    echo Marque a opcao Add Python to PATH, se aparecer.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente do AutoBox. Isso ocorre apenas na primeira vez...
    py -3 -m venv .venv
    if errorlevel 1 goto :erro
)
".venv\Scripts\python.exe" -c "import cv2, pynput, PIL, numpy, playwright" >nul 2>&1
if errorlevel 1 (
    echo Instalando bibliotecas que estao faltando...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :erro
)
echo Abrindo AutoBox...
".venv\Scripts\python.exe" AutoBox_Sem_Mouse.py
if errorlevel 1 goto :erro
exit /b 0
:erro
echo.
echo Algo deu errado. Fotografe o erro desta janela e mande no chat.
pause
exit /b 1
