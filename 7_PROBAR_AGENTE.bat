@echo off
cd /d "%~dp0"
python -m unittest -v test_agente.py test_integracion.py
pause
