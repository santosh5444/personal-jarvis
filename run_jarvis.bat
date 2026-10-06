@echo off
title Jarvis Voice Assistant
cd /d "%~dp0"
echo =================================================================
echo  Launching Jarvis Voice Assistant...
echo =================================================================
call venv\Scripts\activate.bat
python main.py
if errorlevel 1 pause
