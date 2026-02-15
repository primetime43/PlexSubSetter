"""
Constants and configuration values for PlexSubSetter.
"""

# Application metadata
__version__ = "1.7.0"
__author__ = "primetime43"
__repo__ = "https://github.com/primetime43/PlexSubSetter"

# Language mappings for subtitle search
SEARCH_LANGUAGES = {
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Japanese": "ja",
    "Korean": "ko",
    "Chinese": "zh",
    "Russian": "ru",
    "Arabic": "ar",
    "Dutch": "nl",
    "Polish": "pl",
    "Swedish": "sv",
    "Danish": "da",
    "Finnish": "fi",
    "Norwegian": "no"
}

# Subtitle providers
SUBTITLE_PROVIDERS = {
    "OpenSubtitles": "opensubtitles",
    "Podnapisi": "podnapisi",
    "TVSubtitles": "tvsubtitles",
    "Addic7ed": "addic7ed",
    "Subscene": "subscene"
}

# Subtitle Search Configuration
MAX_SUBTITLE_RESULTS = 10  # Maximum number of subtitle options to display per item
DEFAULT_SEARCH_TIMEOUT = 30  # Default subtitle search timeout in seconds
MIN_SEARCH_TIMEOUT = 10  # Minimum search timeout in seconds
MAX_SEARCH_TIMEOUT = 120  # Maximum search timeout in seconds

# Batch Operation Configuration
DEFAULT_BATCH_THRESHOLD = 10  # Default threshold for batch operation confirmation
DEFAULT_CONCURRENT_DOWNLOADS = 3  # Default number of concurrent subtitle downloads

# Retry Configuration
DEFAULT_RETRY_ATTEMPTS = 2  # Default retry attempts for library operations
CRITICAL_RETRY_ATTEMPTS = 3  # Retry attempts for critical operations (server connection)
DEFAULT_RETRY_DELAY = 2.0  # Initial delay between retries in seconds
CRITICAL_RETRY_DELAY = 1.0  # Initial delay for critical operations

# Configuration File — resolve to project root (same directory as run.bat / app.py)
import os as _os
CONFIG_FILE_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'config.ini')

