"""
Configuration manager for PlexSubSetter.

This module provides centralized configuration management for loading and saving
application settings from config.ini file.
"""

import configparser
import logging
from typing import Dict, Any
from utils.constants import (
    CONFIG_FILE_PATH,
    DEFAULT_SEARCH_TIMEOUT,
    DEFAULT_BATCH_THRESHOLD,
    DEFAULT_CONCURRENT_DOWNLOADS
)


class ConfigManager:
    """Manages application configuration loading and saving."""

    # Default configuration values
    DEFAULTS = {
        'General': {
            'subtitle_save_method': 'plex',
            'default_language': 'English',
            'remember_last_library': True,
            'last_library': ''
        },
        'Subtitles': {
            'prefer_hearing_impaired': False,
            'prefer_forced': False,
            'default_providers': 'opensubtitles,podnapisi',
            'search_timeout': DEFAULT_SEARCH_TIMEOUT
        },
        'UI': {
            'show_log_on_startup': False,
            'default_subtitle_filter': 'all',
            'confirm_batch_operations': True,
            'batch_operation_threshold': DEFAULT_BATCH_THRESHOLD
        },
        'Advanced': {
            'concurrent_downloads': DEFAULT_CONCURRENT_DOWNLOADS,
            'enable_debug_logging': False
        }
    }

    def __init__(self, config_path: str = CONFIG_FILE_PATH):
        """
        Initialize the configuration manager.

        Args:
            config_path: Path to the configuration file (defaults to CONFIG_FILE_PATH constant)
        """
        self.config_path = config_path
        self.config = configparser.ConfigParser()

    def load_settings(self) -> Dict[str, Any]:
        """
        Load application settings from config file.

        Returns:
            Dictionary containing all application settings with proper types
        """
        self.config.read(self.config_path)

        settings = {}

        # === General Settings ===
        settings['subtitle_save_method'] = self.config.get(
            'General', 'subtitle_save_method',
            fallback=self.DEFAULTS['General']['subtitle_save_method']
        )
        settings['default_language'] = self.config.get(
            'General', 'default_language',
            fallback=self.DEFAULTS['General']['default_language']
        )
        settings['remember_last_library'] = self.config.getboolean(
            'General', 'remember_last_library',
            fallback=self.DEFAULTS['General']['remember_last_library']
        )
        settings['last_library'] = self.config.get(
            'General', 'last_library',
            fallback=self.DEFAULTS['General']['last_library']
        )

        # === Subtitle Settings ===
        settings['prefer_hearing_impaired'] = self.config.getboolean(
            'Subtitles', 'prefer_hearing_impaired',
            fallback=self.DEFAULTS['Subtitles']['prefer_hearing_impaired']
        )
        settings['prefer_forced'] = self.config.getboolean(
            'Subtitles', 'prefer_forced',
            fallback=self.DEFAULTS['Subtitles']['prefer_forced']
        )
        settings['default_providers'] = self.config.get(
            'Subtitles', 'default_providers',
            fallback=self.DEFAULTS['Subtitles']['default_providers']
        )
        settings['search_timeout'] = self.config.getint(
            'Subtitles', 'search_timeout',
            fallback=self.DEFAULTS['Subtitles']['search_timeout']
        )

        # === UI Settings ===
        settings['show_log_on_startup'] = self.config.getboolean(
            'UI', 'show_log_on_startup',
            fallback=self.DEFAULTS['UI']['show_log_on_startup']
        )
        settings['default_subtitle_filter'] = self.config.get(
            'UI', 'default_subtitle_filter',
            fallback=self.DEFAULTS['UI']['default_subtitle_filter']
        )
        settings['confirm_batch_operations'] = self.config.getboolean(
            'UI', 'confirm_batch_operations',
            fallback=self.DEFAULTS['UI']['confirm_batch_operations']
        )
        settings['batch_operation_threshold'] = self.config.getint(
            'UI', 'batch_operation_threshold',
            fallback=self.DEFAULTS['UI']['batch_operation_threshold']
        )

        # === Advanced Settings ===
        settings['concurrent_downloads'] = self.config.getint(
            'Advanced', 'concurrent_downloads',
            fallback=self.DEFAULTS['Advanced']['concurrent_downloads']
        )
        settings['enable_debug_logging'] = self.config.getboolean(
            'Advanced', 'enable_debug_logging',
            fallback=self.DEFAULTS['Advanced']['enable_debug_logging']
        )

        logging.debug(f"Loaded settings from {self.config_path}")
        return settings

    def save_settings(self, settings: Dict[str, Any]) -> None:
        """
        Save application settings to config file.

        Args:
            settings: Dictionary containing all application settings
        """
        # Read existing config to preserve other sections
        self.config.read(self.config_path)

        # === General Settings ===
        if not self.config.has_section('General'):
            self.config.add_section('General')
        self.config.set('General', 'subtitle_save_method', settings['subtitle_save_method'])
        self.config.set('General', 'default_language', settings['default_language'])
        self.config.set('General', 'remember_last_library', str(settings['remember_last_library']))
        self.config.set('General', 'last_library', settings.get('last_library', ''))

        # === Subtitle Settings ===
        if not self.config.has_section('Subtitles'):
            self.config.add_section('Subtitles')
        self.config.set('Subtitles', 'prefer_hearing_impaired', str(settings['prefer_hearing_impaired']))
        self.config.set('Subtitles', 'prefer_forced', str(settings['prefer_forced']))
        self.config.set('Subtitles', 'default_providers', settings['default_providers'])
        self.config.set('Subtitles', 'search_timeout', str(settings['search_timeout']))

        # === UI Settings ===
        if not self.config.has_section('UI'):
            self.config.add_section('UI')
        self.config.set('UI', 'show_log_on_startup', str(settings['show_log_on_startup']))
        self.config.set('UI', 'default_subtitle_filter', settings['default_subtitle_filter'])
        self.config.set('UI', 'confirm_batch_operations', str(settings['confirm_batch_operations']))
        self.config.set('UI', 'batch_operation_threshold', str(settings['batch_operation_threshold']))

        # === Advanced Settings ===
        if not self.config.has_section('Advanced'):
            self.config.add_section('Advanced')
        self.config.set('Advanced', 'concurrent_downloads', str(settings['concurrent_downloads']))
        self.config.set('Advanced', 'enable_debug_logging', str(settings['enable_debug_logging']))

        # Write to file
        try:
            with open(self.config_path, 'w') as f:
                self.config.write(f)
            logging.debug(f"Saved settings to {self.config_path}")
        except (IOError, OSError) as e:
            logging.error(f"Failed to save settings to {self.config_path}: {e}")
            raise

    def get_default_settings(self) -> Dict[str, Any]:
        """
        Get default application settings.

        Returns:
            Dictionary containing default settings with proper types
        """
        settings = {}

        # Flatten the DEFAULTS structure
        for section in self.DEFAULTS.values():
            settings.update(section)

        return settings
