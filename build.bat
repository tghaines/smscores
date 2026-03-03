@echo off
echo.
echo === Building ScoreScraper.exe ===
echo.

pip install pyinstaller requests
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Make sure Python is installed.
    pause
    exit /b 1
)

echo.
echo Building exe (this takes a minute or two)...
echo.

pyinstaller --onefile --noconsole --name ScoreScraper win_scraper_gui.py
if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo === Done! ===
echo.
echo Your exe is at: dist\ScoreScraper.exe
echo.
pause
