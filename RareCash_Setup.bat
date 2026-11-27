@echo off
title Rare Cash Setup
cd /d "%~dp0"
echo.
echo  ==========================================
echo     RARE CASH - Setup (sirf pehli baar)
echo  ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python nahi mila.
  echo     python.org khul raha hai: Python install karo aur "Add python.exe to PATH" TICK karna.
  echo     Install ke baad ye file dobara double-click karo.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [..] FFmpeg install kar raha hoon ^(video editing ke liye^)...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
)

if not exist ".venv\Scripts\python.exe" (
  echo [..] Rare Cash ka apna Python folder bana raha hoon...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [..] Zaroori packages install ho rahe hain (5-10 minute lag sakte hain)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo [X] Packages install nahi hue. Internet check karke dobara chalao.
  pause
  exit /b 1
)

echo [..] Bot ka browser install ho raha hai...
python -m playwright install chromium

if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo  [OK] Setup ho gaya!
echo  Ab is window ko band karo aur  start_rarecash.bat  double-click karo.
echo  Browser mein dashboard khulega: http://localhost:8000
echo.
pause
