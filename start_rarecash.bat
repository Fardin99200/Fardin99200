@echo off
title Rare Cash
REM Rare Cash - double click karo. Dashboard browser mein khulega: http://localhost:8000
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo Pehle setup chahiye...
  call RareCash_Setup.bat
  exit /b
)
call .venv\Scripts\activate.bat
:loop
python rarecash.py
echo Rare Cash band ho gaya, 30 second mein dobara start...
timeout /t 30 /nobreak
goto loop
