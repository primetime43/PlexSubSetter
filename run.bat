@echo off
REM PlexSubSetter Launcher for Windows

python app.py

if errorlevel 1 (
    echo.
    echo Error running PlexSubSetter
    echo Make sure Python is installed and in your PATH
    echo.
    pause
)
