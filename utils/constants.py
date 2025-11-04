"""
Constants and configuration values for PlexSubSetter.
"""

# Application metadata
__version__ = "1.0.0"
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

# UI Configuration
ITEMS_PER_PAGE = 50  # Pagination size for large libraries
MAX_TITLE_LENGTH = 60  # Maximum title length before truncation

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

# Authentication Configuration
OAUTH_LOGIN_TIMEOUT = 300  # OAuth login timeout in seconds (5 minutes)

# Configuration File
CONFIG_FILE_PATH = 'config.ini'  # Path to application configuration file

# UI Colors
COLOR_PLEX_GOLD = '#e5a00d'  # Plex brand color (primary)
COLOR_PLEX_GOLD_HOVER = '#cc8f0c'  # Plex brand color (hover state)
COLOR_LINK_BLUE = '#58a6ff'  # GitHub-style link color
COLOR_STATUS_GREEN = '#2ecc71'  # Success/online status
COLOR_STATUS_GREEN_DARK = '#236123'  # Dark green for selected items
COLOR_STATUS_GREEN_DARKER = '#2d7a2d'  # Darker green variant
COLOR_STATUS_RED = '#e74c3c'  # Error/offline status
COLOR_STATUS_RED_DARK = '#8b0000'  # Dark red for errors
COLOR_STATUS_RED_DARKER = '#6b0000'  # Darker red variant
COLOR_STATUS_YELLOW = 'yellow'  # Warning/processing status
COLOR_GRAY = 'gray'  # Secondary text color
COLOR_DARK_GRAY = '#404040'  # Dark gray background

# Window Dimensions
# Login window
WINDOW_LOGIN_MIN_WIDTH = 400
WINDOW_LOGIN_MIN_HEIGHT = 500
WINDOW_LOGIN_WIDTH = 500
WINDOW_LOGIN_HEIGHT = 600

# Server selection window
WINDOW_SERVER_MIN_WIDTH = 600
WINDOW_SERVER_MIN_HEIGHT = 500
WINDOW_SERVER_WIDTH = 700
WINDOW_SERVER_HEIGHT = 600

# Main application window
WINDOW_MAIN_MIN_WIDTH = 1000
WINDOW_MAIN_MIN_HEIGHT = 750
WINDOW_MAIN_WIDTH = 1200
WINDOW_MAIN_HEIGHT = 850
