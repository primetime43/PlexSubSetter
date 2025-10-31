# Release Process

This document explains how to create a new release of PlexSubSetter.

## Automatic Builds

PlexSubSetter uses GitHub Actions to automatically build executable files for **Windows, macOS, and Linux** when you create a release.

### Creating a Release

1. **Update the version number** in `plex_subsetter_gui.py`:
   ```python
   __version__ = "1.1.0"  # Update this line
   ```

2. **Commit and push your changes**:
   ```bash
   git add .
   git commit -m "Release v1.1.0"
   git push origin main
   ```

3. **Create a new release on GitHub**:
   - Go to your repository on GitHub
   - Click on "Releases" (right sidebar)
   - Click "Draft a new release"
   - Click "Choose a tag" and create a new tag (e.g., `v1.1.0`)
   - Set the release title (e.g., "PlexSubSetter v1.1.0")
   - Add release notes describing changes
   - Click "Publish release"

4. **Wait for the builds**:
   - GitHub Actions will automatically start building for all 3 platforms
   - Check the "Actions" tab to monitor progress
   - Three jobs run in parallel: `build-windows`, `build-macos`, `build-linux`
   - When complete, executables will be attached to the release:
     - `PlexSubSetter-v1.1.0-Windows.exe`
     - `PlexSubSetter-v1.1.0-macOS` + `PlexSubSetter-v1.1.0-macOS.tar.gz`
     - `PlexSubSetter-v1.1.0-Linux` + `PlexSubSetter-v1.1.0-Linux.tar.gz`

### What Gets Built

The GitHub Action builds for three platforms:

**Windows (windows-latest)**
- ✅ Python 3.12 environment
- ✅ All dependencies from `requirements.txt`
- ✅ Single-file `.exe` using PyInstaller
- ✅ No console window (GUI only)

**macOS (macos-latest)**
- ✅ Python 3.12 environment
- ✅ All dependencies from `requirements.txt`
- ✅ Native macOS executable
- ✅ Tarball for easy distribution

**Linux (ubuntu-latest)**
- ✅ Python 3.12 environment
- ✅ All dependencies + Tkinter system packages
- ✅ Native Linux executable
- ✅ Tarball for easy distribution

### Build Options

The executable is built with these PyInstaller options:
- `--onefile`: Single executable file (no dependencies folder)
- `--windowed`: No console window (GUI only)
- `--name PlexSubSetter`: Names the executable
- `--clean`: Clean build (removes previous artifacts)

## Testing Locally

Before creating a release, you can test the build locally on your platform:

### Windows
```bash
build_exe.bat
```

This will:
1. Install PyInstaller
2. Build the executable
3. Create `dist\PlexSubSetter.exe`

### macOS / Linux
```bash
chmod +x build_exe.sh
./build_exe.sh
```

This will:
1. Install PyInstaller
2. Build the executable
3. Create `dist/PlexSubSetter`
4. Make it executable

### Manual Build (Any Platform)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PlexSubSetter --clean plex_subsetter_gui.py
```

The executable will be in the `dist/` folder:
- Windows: `dist/PlexSubSetter.exe`
- macOS/Linux: `dist/PlexSubSetter`

## Troubleshooting

### Build fails on GitHub Actions
- Check the "Actions" tab for error logs
- Common issues:
  - Missing dependencies in `requirements.txt`
  - Import errors
  - Missing files

### Executable doesn't run
- Test locally first with `build_exe.bat`
- Check for:
  - Missing DLLs
  - Antivirus blocking
  - Windows Defender SmartScreen warning (users need to click "More info" → "Run anyway")

### Executable is too large
- PyInstaller bundles all dependencies
- Expected size: 50-100 MB
- This is normal for Python GUI applications

## Release Checklist

Before creating a release:
- [ ] Update version number in `plex_subsetter_gui.py`
- [ ] Test the application locally
- [ ] Update CLAUDE.md if architecture changed
- [ ] Update README.md if needed
- [ ] Test local build with `build_exe.bat`
- [ ] Commit and push all changes
- [ ] Create release on GitHub
- [ ] Wait for build to complete
- [ ] Test downloaded executable
- [ ] Update release notes if needed
