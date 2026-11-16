@echo off
title YACHAYBOT - Servidor y analitica educativa
cd /d "%~dp0"

echo ============================================================
echo   YACHAYBOT - ARRANCAR EL CEREBRO
echo ============================================================
echo.

if exist clave.txt (
    set /p GROQ_API_KEY=<clave.txt
) else (
    echo No encuentro clave.txt.
    echo Pega tu nueva clave de Groq y presiona Enter.
    set /p GROQ_API_KEY=Clave: 
    echo %GROQ_API_KEY%>clave.txt
)

echo.
echo Direcciones IPv4 disponibles en esta laptop:
ipconfig | findstr /C:"IPv4"
echo.
echo La IP elegida debe coincidir con SERVER_BASE_URL del main.c.
echo Ejemplo: http://192.168.1.4:8000
echo.
echo No cierres esta ventana mientras uses el robot.
echo Para detener el servidor: Ctrl + C
echo Dashboard local: http://127.0.0.1:8000/dashboard
echo ------------------------------------------------------------

python server.py

echo.
echo El servidor se detuvo.
pause
