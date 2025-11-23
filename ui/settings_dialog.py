"""
Settings dialog for PlexSubSetter.

This module provides a comprehensive settings interface with tabs for:
- General settings (language, theme)
- Subtitle preferences (providers, timeout, save method)
- UI/Behavior settings (filters, confirmations)
- Advanced settings (concurrent downloads, debug logging)
"""

import customtkinter as ctk
from tkinter import messagebox
from utils.constants import (
    SEARCH_LANGUAGES,
    MIN_SEARCH_TIMEOUT,
    MAX_SEARCH_TIMEOUT,
    DEFAULT_SEARCH_TIMEOUT,
    DEFAULT_BATCH_THRESHOLD,
    DEFAULT_CONCURRENT_DOWNLOADS
)


class SettingsDialog:
    """Settings dialog window for configuring PlexSubSetter."""

    def __init__(self, parent, current_settings, on_save_callback, log_file_path):
        """
        Initialize settings dialog.

        Args:
            parent: Parent frame/window
            current_settings: Dict of current setting values
            on_save_callback: Function to call when settings are saved
            log_file_path: Path to current log file
        """
        self.parent = parent
        self.current_settings = current_settings
        self.on_save_callback = on_save_callback
        self.log_file_path = log_file_path
        self.settings_window = None
        self.settings_vars = {}

    def make_combobox_clickable(self, combobox):
        """Make entire combobox clickable, not just the arrow button."""
        def open_dropdown(event):
            # Trigger the dropdown to open
            combobox._open_dropdown_menu()

        # Bind click event to the entry part of the combobox
        try:
            # Access the internal entry widget and bind click event
            if hasattr(combobox, '_entry'):
                combobox._entry.configure(cursor="hand2")
                combobox._entry.bind("<Button-1>", open_dropdown)
        except Exception:
            pass  # Silently fail if binding doesn't work

    def show(self):
        """Display the settings dialog."""
        self.settings_window = ctk.CTkToplevel(self.parent)
        self.settings_window.title("PlexSubSetter Settings")
        self.settings_window.geometry("800x650")
        self.settings_window.transient(self.parent)
        self.settings_window.grab_set()

        # Center window
        self.settings_window.update_idletasks()
        x = (self.settings_window.winfo_screenwidth() // 2) - (800 // 2)
        y = (self.settings_window.winfo_screenheight() // 2) - (650 // 2)
        self.settings_window.geometry(f"800x650+{x}+{y}")

        # Create UI
        self._create_layout()
        self._create_tabs()
        self._create_buttons()

    def _create_layout(self):
        """Create main layout structure."""
        # Main container
        self.main_frame = ctk.CTkFrame(self.settings_window)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(self.main_frame, text="⚙ Settings",
                    font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", pady=(0, 15))

        # Create tabview
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.pack(fill="both", expand=True, pady=(0, 15))

    def _create_tabs(self):
        """Create all settings tabs."""
        # Create tabs
        general_tab = self.tabview.add("General")
        subtitles_tab = self.tabview.add("Subtitles")
        ui_tab = self.tabview.add("UI/Behavior")
        advanced_tab = self.tabview.add("Advanced")

        # Populate tabs
        self._create_general_tab(general_tab)
        self._create_subtitles_tab(subtitles_tab)
        self._create_ui_tab(ui_tab)
        self._create_advanced_tab(advanced_tab)

    def _create_general_tab(self, parent):
        """Create General settings tab."""
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Default Language
        ctk.CTkLabel(scroll, text="Default Subtitle Language",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['default_language'] = ctk.StringVar(
            value=self.current_settings.get('default_language', 'English'))
        lang_combo = ctk.CTkComboBox(scroll, values=list(SEARCH_LANGUAGES.keys()),
                                     variable=self.settings_vars['default_language'], state="readonly")
        lang_combo.pack(fill="x", pady=(0, 5))
        self.make_combobox_clickable(lang_combo)
        ctk.CTkLabel(scroll, text="Language used when searching for subtitles",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Appearance Mode
        ctk.CTkLabel(scroll, text="Appearance Theme",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['appearance_mode'] = ctk.StringVar(
            value=self.current_settings.get('appearance_mode', 'dark'))
        appearance_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        appearance_frame.pack(fill="x", pady=(0, 5))
        for mode in ["dark", "light", "system"]:
            ctk.CTkRadioButton(appearance_frame, text=mode.capitalize(),
                              variable=self.settings_vars['appearance_mode'],
                              value=mode).pack(side="left", padx=(0, 20))
        ctk.CTkLabel(scroll, text="Choose the color theme for the application",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Remember Last Library
        self.settings_vars['remember_last_library'] = ctk.BooleanVar(
            value=self.current_settings.get('remember_last_library', True))
        ctk.CTkCheckBox(scroll, text="Remember last selected library",
                       variable=self.settings_vars['remember_last_library']).pack(anchor="w", pady=(5, 5))
        ctk.CTkLabel(scroll, text="Automatically select the last used library when opening the app",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

    def _create_subtitles_tab(self, parent):
        """Create Subtitles settings tab."""
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Subtitle Save Method
        ctk.CTkLabel(scroll, text="Subtitle Save Method",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['subtitle_save_method'] = ctk.StringVar(
            value=self.current_settings.get('subtitle_save_method', 'plex'))

        save_method_frame = ctk.CTkFrame(scroll, fg_color=("gray85", "gray20"))
        save_method_frame.pack(fill="x", pady=(0, 5))

        ctk.CTkRadioButton(save_method_frame, text="Upload to Plex (Recommended)",
                          variable=self.settings_vars['subtitle_save_method'],
                          value="plex").pack(anchor="w", padx=15, pady=(10, 5))
        ctk.CTkLabel(save_method_frame,
                    text="  • Subtitles uploaded to Plex's internal database\n"
                         "  • Works with remote servers\n"
                         "  • Subtitles survive if video files move",
                    font=ctk.CTkFont(size=11), text_color="gray",
                    justify="left").pack(anchor="w", padx=30, pady=(0, 10))

        ctk.CTkRadioButton(save_method_frame, text="Save next to video file",
                          variable=self.settings_vars['subtitle_save_method'],
                          value="file").pack(anchor="w", padx=15, pady=(5, 5))
        ctk.CTkLabel(save_method_frame,
                    text="  • Subtitles saved alongside video files\n"
                         "  • Requires local or network file access\n"
                         "  • Plex auto-detects on next scan",
                    font=ctk.CTkFont(size=11), text_color="gray",
                    justify="left").pack(anchor="w", padx=30, pady=(0, 10))

        # Subtitle Preferences
        ctk.CTkLabel(scroll, text="Subtitle Preferences",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(15, 5))

        self.settings_vars['prefer_hearing_impaired'] = ctk.BooleanVar(
            value=self.current_settings.get('prefer_hearing_impaired', False))
        ctk.CTkCheckBox(scroll, text="Prefer hearing impaired (SDH) subtitles",
                       variable=self.settings_vars['prefer_hearing_impaired']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(scroll, text="Prioritize subtitles with sound descriptions",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 10))

        self.settings_vars['prefer_forced'] = ctk.BooleanVar(
            value=self.current_settings.get('prefer_forced', False))
        ctk.CTkCheckBox(scroll, text="Prefer forced subtitles",
                       variable=self.settings_vars['prefer_forced']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(scroll, text="Subtitles only for foreign language parts",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 15))

        # Default Providers
        ctk.CTkLabel(scroll, text="Default Subtitle Providers",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['default_providers'] = ctk.StringVar(
            value=self.current_settings.get('default_providers', 'opensubtitles,podnapisi'))
        providers_entry = ctk.CTkEntry(scroll, textvariable=self.settings_vars['default_providers'])
        providers_entry.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(scroll,
                    text="Comma-separated list: opensubtitles, podnapisi, tvsubtitles, addic7ed",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Search Timeout
        ctk.CTkLabel(scroll, text="Search Timeout (seconds)",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['search_timeout'] = ctk.IntVar(
            value=self.current_settings.get('search_timeout', DEFAULT_SEARCH_TIMEOUT))
        timeout_slider = ctk.CTkSlider(scroll, from_=MIN_SEARCH_TIMEOUT, to=MAX_SEARCH_TIMEOUT,
                                       variable=self.settings_vars['search_timeout'],
                                       number_of_steps=22)
        timeout_slider.pack(fill="x", pady=(0, 5))
        timeout_label = ctk.CTkLabel(scroll, text=f"{self.settings_vars['search_timeout'].get()} seconds")
        timeout_label.pack(anchor="w", pady=(0, 5))

        def update_timeout_label(*args):
            timeout_label.configure(text=f"{self.settings_vars['search_timeout'].get()} seconds")
        self.settings_vars['search_timeout'].trace_add("write", update_timeout_label)

        ctk.CTkLabel(scroll, text="Maximum time to wait for subtitle search results",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

    def _create_ui_tab(self, parent):
        """Create UI/Behavior settings tab."""
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Show Log on Startup
        ctk.CTkLabel(scroll, text="Startup Behavior",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['show_log_on_startup'] = ctk.BooleanVar(
            value=self.current_settings.get('show_log_on_startup', False))
        ctk.CTkCheckBox(scroll, text="Show log panel on startup",
                       variable=self.settings_vars['show_log_on_startup']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(scroll, text="Display the activity log when the application starts",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 15))

        # Default Subtitle Filter
        ctk.CTkLabel(scroll, text="Default Subtitle Filter",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['default_subtitle_filter'] = ctk.StringVar(
            value=self.current_settings.get('default_subtitle_filter', 'all'))
        filter_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        filter_frame.pack(fill="x", pady=(0, 5))
        for filter_opt in ["all", "missing", "has"]:
            ctk.CTkRadioButton(filter_frame, text=filter_opt.capitalize(),
                              variable=self.settings_vars['default_subtitle_filter'],
                              value=filter_opt).pack(side="left", padx=(0, 15))
        ctk.CTkLabel(scroll, text="Default filter when viewing libraries",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Batch Operation Confirmations
        ctk.CTkLabel(scroll, text="Batch Operations",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['confirm_batch_operations'] = ctk.BooleanVar(
            value=self.current_settings.get('confirm_batch_operations', True))
        ctk.CTkCheckBox(scroll, text="Confirm before batch operations",
                       variable=self.settings_vars['confirm_batch_operations']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(scroll, text="Show confirmation dialog before processing multiple items",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 10))

        # Batch Operation Threshold
        ctk.CTkLabel(scroll, text="Batch operation threshold:",
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(5, 5))
        self.settings_vars['batch_operation_threshold'] = ctk.IntVar(
            value=self.current_settings.get('batch_operation_threshold', DEFAULT_BATCH_THRESHOLD))
        threshold_slider = ctk.CTkSlider(scroll, from_=5, to=50,
                                        variable=self.settings_vars['batch_operation_threshold'],
                                        number_of_steps=9)
        threshold_slider.pack(fill="x", pady=(0, 5))
        threshold_label = ctk.CTkLabel(scroll, text=f"{self.settings_vars['batch_operation_threshold'].get()} items")
        threshold_label.pack(anchor="w", pady=(0, 5))

        def update_threshold_label(*args):
            threshold_label.configure(text=f"{self.settings_vars['batch_operation_threshold'].get()} items")
        self.settings_vars['batch_operation_threshold'].trace_add("write", update_threshold_label)

        ctk.CTkLabel(scroll, text="Show warning when operating on this many items or more",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

    def _create_advanced_tab(self, parent):
        """Create Advanced settings tab."""
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(scroll, text="⚠ Advanced Settings",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color="#e5a00d").pack(anchor="w", pady=(5, 5))
        ctk.CTkLabel(scroll, text="Modify these settings only if you know what you're doing",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Concurrent Downloads
        ctk.CTkLabel(scroll, text="Concurrent Downloads",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        self.settings_vars['concurrent_downloads'] = ctk.IntVar(
            value=self.current_settings.get('concurrent_downloads', DEFAULT_CONCURRENT_DOWNLOADS))
        concurrent_slider = ctk.CTkSlider(scroll, from_=1, to=10,
                                         variable=self.settings_vars['concurrent_downloads'],
                                         number_of_steps=9)
        concurrent_slider.pack(fill="x", pady=(0, 5))
        concurrent_label = ctk.CTkLabel(scroll, text=f"{self.settings_vars['concurrent_downloads'].get()} downloads")
        concurrent_label.pack(anchor="w", pady=(0, 5))

        def update_concurrent_label(*args):
            concurrent_label.configure(text=f"{self.settings_vars['concurrent_downloads'].get()} downloads")
        self.settings_vars['concurrent_downloads'].trace_add("write", update_concurrent_label)

        ctk.CTkLabel(scroll, text="Maximum number of simultaneous subtitle downloads",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Debug Logging
        self.settings_vars['enable_debug_logging'] = ctk.BooleanVar(
            value=self.current_settings.get('enable_debug_logging', False))
        ctk.CTkCheckBox(scroll, text="Enable debug logging",
                       variable=self.settings_vars['enable_debug_logging']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(scroll, text="Write detailed debug information to log files (increases log size)",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 15))

        # Log file location
        ctk.CTkLabel(scroll, text="Current log file:",
                    font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(10, 5))
        log_path_frame = ctk.CTkFrame(scroll, fg_color=("gray85", "gray20"))
        log_path_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(log_path_frame, text=self.log_file_path,
                    font=ctk.CTkFont(size=10, family="Courier"),
                    text_color="gray").pack(anchor="w", padx=10, pady=10)

    def _create_buttons(self):
        """Create dialog buttons (Save, Cancel, Reset)."""
        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))

        reset_btn = ctk.CTkButton(button_frame, text="Reset to Defaults",
                                  command=self._reset_to_defaults,
                                  width=130, fg_color="transparent", border_width=2,
                                  border_color=("gray60", "gray40"),
                                  text_color=("gray10", "gray90"))
        reset_btn.pack(side="left")

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel",
                                   command=self.settings_window.destroy,
                                   width=100, fg_color="transparent", border_width=2,
                                   text_color=("gray10", "gray90"))
        cancel_btn.pack(side="right", padx=(10, 0))

        save_btn = ctk.CTkButton(button_frame, text="Save Settings",
                                command=self._save_and_close,
                                width=120)
        save_btn.pack(side="right")

    def _save_and_close(self):
        """Save settings and close dialog."""
        # Collect all settings from UI variables
        updated_settings = {
            'subtitle_save_method': self.settings_vars['subtitle_save_method'].get(),
            'default_language': self.settings_vars['default_language'].get(),
            'appearance_mode': self.settings_vars['appearance_mode'].get(),
            'remember_last_library': self.settings_vars['remember_last_library'].get(),
            'prefer_hearing_impaired': self.settings_vars['prefer_hearing_impaired'].get(),
            'prefer_forced': self.settings_vars['prefer_forced'].get(),
            'default_providers': self.settings_vars['default_providers'].get(),
            'search_timeout': self.settings_vars['search_timeout'].get(),
            'show_log_on_startup': self.settings_vars['show_log_on_startup'].get(),
            'default_subtitle_filter': self.settings_vars['default_subtitle_filter'].get(),
            'confirm_batch_operations': self.settings_vars['confirm_batch_operations'].get(),
            'batch_operation_threshold': self.settings_vars['batch_operation_threshold'].get(),
            'concurrent_downloads': self.settings_vars['concurrent_downloads'].get(),
            'enable_debug_logging': self.settings_vars['enable_debug_logging'].get(),
        }

        # Call parent's save callback
        self.on_save_callback(updated_settings)

        # Close dialog
        self.settings_window.destroy()

    def _reset_to_defaults(self):
        """Reset all settings to default values."""
        if messagebox.askyesno("Reset Settings", "Reset all settings to default values?",
                              parent=self.settings_window):
            self.settings_vars['subtitle_save_method'].set('plex')
            self.settings_vars['default_language'].set('English')
            self.settings_vars['appearance_mode'].set('dark')
            self.settings_vars['remember_last_library'].set(True)
            self.settings_vars['prefer_hearing_impaired'].set(False)
            self.settings_vars['prefer_forced'].set(False)
            self.settings_vars['default_providers'].set('opensubtitles,podnapisi')
            self.settings_vars['search_timeout'].set(DEFAULT_SEARCH_TIMEOUT)
            self.settings_vars['show_log_on_startup'].set(False)
            self.settings_vars['default_subtitle_filter'].set('all')
            self.settings_vars['confirm_batch_operations'].set(True)
            self.settings_vars['batch_operation_threshold'].set(DEFAULT_BATCH_THRESHOLD)
            self.settings_vars['concurrent_downloads'].set(DEFAULT_CONCURRENT_DOWNLOADS)
            self.settings_vars['enable_debug_logging'].set(False)
