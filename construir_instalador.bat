@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Dirigivel Meet Guard - gerando instalador
echo ==========================================================
echo   Dirigivel Meet Guard - gerando o instalador
echo ==========================================================
echo.

:: 1) Python ---------------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado.
    echo Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH".
    goto :falha
)

:: 2) Bibliotecas -----------------------------------------------------------
echo [1/4] Instalando bibliotecas...
python -m pip install --upgrade --quiet pip
python -m pip install --upgrade --quiet -r requirements.txt
if errorlevel 1 ( echo [ERRO] Falha ao instalar bibliotecas. & goto :falha )

:: 3) Marca (icone, imagens, versao) ----------------------------------------
echo [2/4] Gerando icone e imagens da marca...
python gerar_marca.py
if errorlevel 1 ( echo [ERRO] Falha ao gerar a marca. & goto :falha )

:: 4) Programa ---------------------------------------------------------------
echo [3/4] Gerando o programa (pode levar alguns minutos)...
taskkill /im MeetGuard.exe /f >nul 2>&1
python -m PyInstaller --noconfirm --clean --log-level WARN ^
    --onedir --noconsole --uac-admin ^
    --name MeetGuard ^
    --icon "build\recursos\app.ico" ^
    --version-file "build\versao.txt" ^
    --add-data "build\recursos;recursos" ^
    --collect-all customtkinter ^
    --hidden-import pystray._win32 ^
    meetguard.py
if errorlevel 1 ( echo [ERRO] Falha ao gerar o programa. & goto :falha )

:: 5) Inno Setup -------------------------------------------------------------
echo [4/4] Montando o instalador...
call :acharISCC
if not defined ISCC (
    echo Inno Setup nao encontrado. Instalando pelo winget...
    winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
    call :acharISCC
)
if not defined ISCC (
    echo [ERRO] Nao consegui instalar o Inno Setup automaticamente.
    echo Baixe em https://jrsoftware.org/isdl.php , instale e rode este arquivo de novo.
    goto :falha
)
"%ISCC%" /Qp MeetGuard.iss
if errorlevel 1 ( echo [ERRO] Falha ao montar o instalador. & goto :falha )

echo.
echo ==========================================================
echo   Pronto! O instalador esta na pasta "instalador".
echo ==========================================================
explorer "%~dp0instalador"
pause
exit /b 0

:acharISCC
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
exit /b 0

:falha
echo.
pause
exit /b 1
