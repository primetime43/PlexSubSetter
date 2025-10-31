@echo off
REM Local build script for PlexSubSetter executable
REM This builds the same way GitHub Actions will

echo ============================================
echo PlexSubSetter - Local Executable Builder
echo ============================================
echo.

echo [1/3] Installing PyInstaller...
pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    pause
    exit /b 1
)

echo.
echo [2/3] Building executable...
pyinstaller --onefile --windowed --name PlexSubSetter --clean plex_subsetter_gui.py
if errorlevel 1 (
    echo ERROR: Build failed
    pause
    exit /b 1
)

echo.
echo [3/3] Build complete!
echo.
echo Executable location: dist\PlexSubSetter.exe
echo.
echo You can now run: dist\PlexSubSetter.exe
echo.
pause
