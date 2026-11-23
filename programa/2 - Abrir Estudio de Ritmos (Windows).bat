@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Rode primeiro "1 - Instalar (Windows).bat" & pause & exit /b 1)
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 (echo. & echo O programa fechou com erro. Tire um print desta janela e mande. & pause)
