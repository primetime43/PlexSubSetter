#!/bin/bash
# Local build script for PlexSubSetter executable (macOS/Linux)
# This builds the same way GitHub Actions will

echo "============================================"
echo "PlexSubSetter - Local Executable Builder"
echo "============================================"
echo ""

# Detect OS
OS=$(uname -s)
echo "Detected OS: $OS"
echo ""

echo "[1/3] Installing PyInstaller..."
pip3 install pyinstaller
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install PyInstaller"
    exit 1
fi

echo ""
echo "[2/3] Building executable..."
pyinstaller --onefile --windowed --name PlexSubSetter --clean plex_subsetter_gui.py
if [ $? -ne 0 ]; then
    echo "ERROR: Build failed"
    exit 1
fi

echo ""
echo "[3/3] Making executable..."
chmod +x dist/PlexSubSetter

echo ""
echo "Build complete!"
echo ""
echo "Executable location: dist/PlexSubSetter"
echo ""

if [ "$OS" == "Darwin" ]; then
    echo "macOS: You can run: ./dist/PlexSubSetter"
    echo "       Or double-click dist/PlexSubSetter in Finder"
elif [ "$OS" == "Linux" ]; then
    echo "Linux: You can run: ./dist/PlexSubSetter"
fi

echo ""
