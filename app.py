#!/usr/bin/env python3
"""
PlexSubSetter - Mass Subtitle Finder and Setter for Plex
Flask web application entry point.
"""

import webbrowser
import threading
import logging

# Fix PlexAPI client identifier for packaged .exe files
import plexapi

from utils.constants import __version__
from utils.logging_config import setup_logging

# Set PlexAPI client headers
plexapi.X_PLEX_IDENTIFIER = "PlexSubSetter"
plexapi.X_PLEX_PRODUCT = "PlexSubSetter"
plexapi.X_PLEX_VERSION = __version__
plexapi.X_PLEX_DEVICE = "PC"
plexapi.X_PLEX_PLATFORM = "Windows"

# Initialize logging
current_log_file = setup_logging()

# Log PlexAPI client configuration
logging.info(f"PlexAPI Client ID: {plexapi.X_PLEX_IDENTIFIER}")
logging.info(f"PlexAPI Product: {plexapi.X_PLEX_PRODUCT}")
logging.info(f"PlexAPI Version: {plexapi.X_PLEX_VERSION}")


def main():
    """Main entry point."""
    from web import create_app

    app = create_app()
    app.state.current_log_file = current_log_file

    port = 5000
    url = f"http://localhost:{port}"

    # Open browser after a short delay (let Flask start first)
    def open_browser():
        import time
        time.sleep(1.0)
        logging.info(f"Opening browser: {url}")
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    logging.info(f"Starting PlexSubSetter web server on {url}")
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
