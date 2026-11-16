@echo off
cd /d "%~dp0"
title YACHAYBOT - Agente docente
echo 1. Ollama local
echo 2. Groq con la clave que ya usas en el robot
set /p OPCION=Elige proveedor [1]: 
set YACHAYBOT_AGENT_PROVIDER=ollama
set YACHAYBOT_AGENT_MODEL=qwen3:4b
if "%OPCION%"=="2" (
  set YACHAYBOT_AGENT_PROVIDER=groq
  set YACHAYBOT_AGENT_MODEL=openai/gpt-oss-20b
)
echo.
echo Ollama requiere servicio iniciado y modelo descargado.
echo Agente: http://127.0.0.1:8000/agente
echo Panel: http://127.0.0.1:8000/dashboard?dias=0
python server.py
pause
