"""
Logging configuration for PlexSubSetter.
"""

import logging
import os
import sys
from datetime import datetime
from utils.constants import __version__


def setup_logging():
    """
    Configure logging to file and console.

    Returns:
        str: Path to the current log file
    """
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create log filename with timestamp
    log_filename = os.path.join(
        log_dir,
        f"plexsubsetter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.info("=" * 80)
    logging.info(f"PlexSubSetter v{__version__} - Session Started")
    logging.info("=" * 80)

    return log_filename
