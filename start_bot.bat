@echo off
REM Vyro bot - double click, ya Task Scheduler mein "At log on" pe lagao
cd /d "%~dp0"
call .venv\Scripts\activate.bat
:loop
python bot.py
echo Bot band ho gaya, 60 second mein dobara start...
timeout /t 60 /nobreak
goto loop
