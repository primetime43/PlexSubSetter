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
