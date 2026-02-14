"""Settings routes."""

import logging
from flask import Blueprint, render_template, jsonify, request

from utils.config_manager import ConfigManager
from utils.constants import (
    SEARCH_LANGUAGES,
    MIN_SEARCH_TIMEOUT,
    MAX_SEARCH_TIMEOUT,
)

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings')
def get_settings():
    """Get current settings as HTML partial (for modal)."""
    config = ConfigManager()
    settings = config.load_settings()
    return render_template('partials/settings_modal.html',
                           settings=settings,
                           languages=SEARCH_LANGUAGES,
                           min_timeout=MIN_SEARCH_TIMEOUT,
                           max_timeout=MAX_SEARCH_TIMEOUT)


@settings_bp.route('/settings', methods=['PUT'])
def update_settings():
    """Update settings."""
    config = ConfigManager()
    data = request.json

    # Build settings dict from request
    settings = {
        'subtitle_save_method': data.get('subtitle_save_method', 'plex'),
        'default_language': data.get('default_language', 'English'),
        'appearance_mode': data.get('appearance_mode', 'dark'),
        'remember_last_library': data.get('remember_last_library', True),
        'last_library': data.get('last_library', ''),
        'prefer_hearing_impaired': data.get('prefer_hearing_impaired', False),
        'prefer_forced': data.get('prefer_forced', False),
        'default_providers': data.get('default_providers', 'opensubtitles,podnapisi'),
        'search_timeout': int(data.get('search_timeout', 30)),
        'show_log_on_startup': data.get('show_log_on_startup', False),
        'default_subtitle_filter': data.get('default_subtitle_filter', 'all'),
        'confirm_batch_operations': data.get('confirm_batch_operations', True),
        'batch_operation_threshold': int(data.get('batch_operation_threshold', 10)),
        'concurrent_downloads': int(data.get('concurrent_downloads', 3)),
        'enable_debug_logging': data.get('enable_debug_logging', False),
    }

    try:
        config.save_settings(settings)

        # Apply debug logging change
        if settings['enable_debug_logging']:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

        return jsonify({'status': 'ok'})
    except Exception as e:
        logging.error(f"Error saving settings: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings/reset', methods=['POST'])
def reset_settings():
    """Reset settings to defaults."""
    config = ConfigManager()
    defaults = config.get_default_settings()
    try:
        config.save_settings(defaults)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
