@echo off
title YACHAYBOT - Prueba completa sin ESP32
cd /d "%~dp0"

echo ============================================================
echo   PRUEBA: WAKE WORD + PREGUNTA + RESPUESTA
echo ============================================================
echo.
echo Deja 2_ARRANCAR.bat abierto.
echo Primero diras Yachaybot. Luego haras una pregunta.
echo.
pause

python probar_sin_robot.py

echo.
pause
