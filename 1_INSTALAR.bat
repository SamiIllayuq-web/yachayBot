@echo off
title YACHAYBOT - Instalacion actualizada
cd /d "%~dp0"

echo ============================================================
echo   YACHAYBOT - INSTALACION DEL SERVIDOR
echo ============================================================
echo.

python --version
if errorlevel 1 (
    echo ERROR: instala Python y marca Add Python to PATH.
    pause
    exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR instalando dependencias.
    pause
    exit /b 1
)

python descargar_voz.py
if errorlevel 1 (
    echo ERROR descargando la voz.
    pause
    exit /b 1
)

echo.
echo LISTO. Ahora abre 2_ARRANCAR.bat
pause
