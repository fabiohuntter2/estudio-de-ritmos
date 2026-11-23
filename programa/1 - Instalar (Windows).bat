@echo off
cd /d "%~dp0"
echo ==========================================
echo   Estudio de Ritmos - instalacao
echo ==========================================
echo.
rem --- procura um Python compativel (3.12 de preferencia; 3.13 ou 3.11 tambem servem)
set PY=
for %%V in (3.12 3.13 3.11) do (
  if not defined PY (
    py -%%V --version >nul 2>nul && set PY=py -%%V
  )
)
if not defined PY (
  echo Nao encontrei o Python 3.12 neste computador.
  echo.
  echo O programa precisa do Python 3.12 - versoes muito novas, como 3.14 e 3.15,
  echo ainda nao tem todas as bibliotecas de audio prontas.
  echo Voce NAO precisa desinstalar o Python que ja tem: os dois convivem.
  echo.
  echo 1. Baixe: https://www.python.org/downloads/release/python-31210/
  echo    role ate o fim e clique em "Windows installer (64-bit)"
  echo 2. Instale, marcando "Add python.exe to PATH"
  echo 3. Rode este instalador de novo.
  echo.
  start "" "https://www.python.org/downloads/release/python-31210/"
  pause
  exit /b 1
)
echo Usando:
%PY% --version
echo.
if exist ".venv" (
  echo Removendo instalacao anterior...
  rmdir /s /q ".venv"
)
echo Criando ambiente...
%PY% -m venv .venv
if errorlevel 1 (echo Falha ao criar o ambiente. Tire um print e mande. & pause & exit /b 1)
set VPY=".venv\Scripts\python.exe"
%VPY% -m pip install --upgrade pip >nul
echo.
echo [1/2] Bibliotecas principais (alguns minutos)...
%VPY% -m pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 (echo. & echo Falhou nas bibliotecas principais. Tire um print desta janela e mande. & pause & exit /b 1)
echo.
echo [2/2] Bibliotecas opcionais...
set FALTOU=
%VPY% -m pip install --only-binary=:all: "sounddevice>=0.4.6" || set FALTOU=%FALTOU% [som-pela-placa]
%VPY% -m pip install --only-binary=:all: "python-rtmidi>=1.5" || set FALTOU=%FALTOU% [teclado-MIDI]
%VPY% -m pip install --only-binary=:all: "pedalboard>=0.9.10" || set FALTOU=%FALTOU% [VST-Kontakt]
echo.
echo Rodando os testes automaticos...
%VPY% -m unittest discover -s testes -p "test_*.py"
echo.
if defined FALTOU (
  echo ATENCAO: nao instalou:%FALTOU%
  echo O programa abre normalmente, mas sem esses recursos. Tire um print e mande.
) else (
  echo Tudo instalado.
)
echo.
echo Pronto! Abra o programa com "2 - Abrir Estudio de Ritmos (Windows).bat"
pause
