@echo off
REM PlexSubSetter GUI Launcher for Windows

python plex_subsetter_gui.py

if errorlevel 1 (
    echo.
    echo Error running PlexSubSetter GUI
    echo Make sure Python is installed and in your PATH
    echo.
    pause
)
