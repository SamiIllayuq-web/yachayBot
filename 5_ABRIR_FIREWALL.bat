@echo off
chcp 65001 >nul
title YACHAYBOT - Firewall e IP

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

netsh advfirewall firewall delete rule name="YACHAYBOT" >nul 2>&1
netsh advfirewall firewall add rule name="YACHAYBOT" dir=in action=allow protocol=TCP localport=8000

echo.
echo Puerto TCP 8000 abierto.
echo Direcciones IPv4 de esta laptop:
ipconfig | findstr /C:"IPv4"
echo.
echo En main.c configura:
echo #define SERVER_BASE_URL "http://IP_DE_TU_LAPTOP:8000"
echo.
echo Prueba el servidor en: http://127.0.0.1:8000/ping
pause
