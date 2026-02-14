# PlexSubSetter

Stop going episode by episode to set subtitles in Plex! PlexSubSetter lets you search, download, and manage subtitles for entire seasons, shows, or your whole movie library at once. This will allow you to set the subtitles easily.

![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

## Table of Contents
- [Why I Built This](#why-i-built-this)
- [What It Does](#what-it-does)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [How to Use](#how-to-use)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Why I Built This

I got tired of going through TV shows episode by episode in Plex, manually setting subtitles for each one that was missing. PlexSubSetter makes it easy to:

- **Find missing subtitles** across entire seasons or libraries
- **Batch download** for multiple episodes/movies at once
- **Set subtitles automatically** without clicking through every item
- **Manage subtitles** easily - see what's there, delete what you don't want

Whether you're missing subtitles on a few episodes or want to add them to your entire library, this tool does it all in a few clicks instead of hours of manual work.

## What It Does

### Main Features
- **Batch Subtitle Downloads** - Select multiple episodes, seasons, or movies and download subtitles for all of them at once
- **Smart Filtering** - Quickly see which items are missing subtitles vs. which already have them
- **Multiple Providers** - Searches OpenSubtitles, Podnapisi, and other subtitle sources automatically
- **Preview Before Download** - See what subtitles are available before downloading
- **Manage Existing Subtitles** - View, activate, or delete subtitle streams
- **Multi-Language Support** - Download subtitles in any language
- **Web-Based UI** - Runs in your browser with a dark-themed modern interface

## Installation

### Prerequisites
- Python 3.8 or higher
- Plex Media Server
- Plex account

### Install Dependencies

```bash
pip install -r requirements.txt
```

**Required packages:**
- `plexapi>=4.15.0` - Plex API client
- `flask>=3.0` - Web framework
- `subliminal>=2.1.0` - Subtitle search and download
- `babelfish>=0.6.0` - Language handling

## Quick Start

**Windows:**
```batch
run.bat
```
or
```bash
python app.py
```

**Linux/Mac:**
```bash
./run.sh
```
or
```bash
python3 app.py
```

The app starts a local web server on `http://localhost:5000` and opens your browser automatically.

## Configuration

PlexSubSetter stores all your settings in a `config.ini` file in the application directory. You can change settings two ways:

1. **Through the web UI** - Click the Settings button (easy, recommended)
2. **Edit config.ini directly** - For advanced users or automation

All settings are saved automatically and persist between sessions. No need to reconfigure every time you open the app!

### Settings Options

#### General
```ini
[General]
subtitle_save_method = plex        # "plex" or "file"
default_language = English         # Default subtitle language
remember_last_library = True       # Remember last selected library
last_library =                     # Auto-populated
```

#### Subtitles
```ini
[Subtitles]
prefer_hearing_impaired = False    # Prefer SDH subtitles
prefer_forced = False              # Prefer forced subtitles
default_providers = opensubtitles,podnapisi  # Comma-separated providers
search_timeout = 30                # Search timeout in seconds
```

#### UI/Behavior
```ini
[UI]
default_subtitle_filter = all      # "all", "missing", or "has"
confirm_batch_operations = True    # Confirm large batch operations
batch_operation_threshold = 10     # Items count for confirmation
```

#### Advanced
```ini
[Advanced]
concurrent_downloads = 3           # Parallel download limit
enable_debug_logging = False       # Enable debug logging
```

### How Subtitles Are Stored

You can choose how PlexSubSetter saves downloaded subtitles:

- **plex** (default): Subtitles are stored in Plex's database. Requires Plex Pass and subtitle agents to be enabled in Plex settings. This keeps subtitles attached to the media item in Plex.

- **file**: Subtitles are saved as separate .srt files next to your video files (e.g., `Movie.mkv` + `Movie.en.srt`). Works without Plex Pass but requires the app to have access to your media file locations.

## How to Use

### First Time Setup
1. Run `python app.py` - your browser opens automatically
2. Click "Sign in with Plex" - a new tab opens for Plex authentication
3. Authorize the app on Plex.tv
4. Choose your Plex server from the list (it picks the best connection automatically)
5. Select a library (Movies, TV Shows, etc.)

### Finding and Downloading Subtitles

**For entire seasons or shows:**
1. Click the arrow to expand a show
2. Check the box next to season(s) or individual episodes
3. Click "Search Available" to see what subtitles are available
4. Click "Download Selected Subtitles" to download them all at once

**For movies:**
1. Use the **Missing** button to see only movies without subtitles
2. Click "Select All" to select everything, or check individual movies
3. Click "Search Available" then "Download Selected Subtitles"

**Quick search:** Type in the search box at the top to filter by title

### Other Useful Features

- **List Current** - See what subtitle streams are already on selected items
- **Dry Run** - Preview which items have subtitles available without downloading
- **Delete** - Remove subtitle streams you don't want
- **Settings** - Change language, providers, and other options
- **All/Missing/Has Subs buttons** - Quickly filter your library by subtitle status
- **Reload Library** - Refresh the view after making changes in Plex

## Architecture

PlexSubSetter uses a web-based architecture with Flask backend and htmx + Alpine.js frontend:

```
PlexSubSetter/
├── app.py                         # Flask entry point
├── plex_subsetter.py              # CLI entry point
├── core/                          # Business logic (no UI)
│   ├── session_state.py           # In-memory session state
│   ├── task_manager.py            # Background tasks + SSE
│   ├── auth_service.py            # Plex OAuth
│   ├── server_service.py          # Server discovery/connection
│   ├── library_service.py         # Library browsing
│   └── subtitle_service.py        # Subtitle operations
├── web/                           # Flask web application
│   ├── __init__.py                # App factory
│   ├── routes/                    # Route blueprints
│   │   ├── auth.py                # Authentication routes
│   │   ├── servers.py             # Server selection
│   │   ├── libraries.py           # Library browsing
│   │   ├── subtitles.py           # Subtitle operations
│   │   ├── settings.py            # Settings management
│   │   ├── events.py              # SSE endpoint
│   │   └── logs.py                # Log viewer
│   ├── templates/                 # Jinja2 templates
│   │   ├── base.html              # Base layout
│   │   ├── login.html             # Login page
│   │   ├── servers.html           # Server selection
│   │   ├── app.html               # Main app (two-column)
│   │   └── partials/              # htmx partial templates
│   └── static/                    # CSS and JavaScript
├── utils/                         # Utility modules
│   ├── config_manager.py          # Configuration management
│   ├── constants.py               # Shared constants
│   ├── logging_config.py          # Logging setup
│   └── security.py                # Security utilities
├── error_handling.py              # Error handling & logging
└── config.ini                     # User configuration
```

### Key Design Patterns
- **Service Layer**: All business logic in `core/` with no UI dependencies
- **SSE (Server-Sent Events)**: Real-time progress updates from background tasks
- **htmx**: Server-rendered HTML partials for dynamic content
- **Alpine.js**: Lightweight reactive state for UI interactions
- **Background Tasks**: Long operations run in threads, push events via SSE
- **Lazy Loading**: Shows/seasons expand on demand for performance
- **Caching**: Subtitle status cached to prevent redundant API calls

## Troubleshooting

### App won't start
- Ensure Python 3.8+ is installed: `python --version`
- Install dependencies: `pip install -r requirements.txt`
- Check logs in `logs/` directory
- Make sure port 5000 is available

### Can't find subtitles
- Verify internet connection
- Check that subtitle providers are accessible
- Try increasing `search_timeout` in settings
- Ensure correct language code is selected

### Connection issues
- Try different server connections (local vs remote)
- Check firewall settings
- Verify Plex server is running
- Check Plex token validity

### Subtitle indicators not updating
- Click "Reload Library" to refresh
- Check that items have been reloaded from server
- Verify subtitle streams are actually present in Plex

## License

MIT License - See LICENSE file for details
