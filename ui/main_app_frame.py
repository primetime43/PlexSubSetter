"""
Main application frame for subtitle management.

This module contains the MainAppFrame class which provides the primary UI
for managing subtitles in Plex libraries, including search, download, set,
upload, and delete operations.
"""

import customtkinter as ctk
from tkinter import messagebox, TclError
import threading
import os
import sys
import tempfile
import logging
from plexapi.video import Movie, Episode, Show
from subliminal import region, download_subtitles
from babelfish import Language
from utils.config_manager import ConfigManager
from ui.settings_dialog import SettingsDialog
from ui.subtitle_operations import SubtitleOperations
from ui.library_browser import LibraryBrowser
from error_handling import (
    retry_with_backoff,
    get_crash_reporter,
    ErrorContext,
    PlexConnectionError,
    PlexAuthenticationError
)
from utils.constants import (
    SEARCH_LANGUAGES,
    SUBTITLE_PROVIDERS,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_DELAY
)


class MainAppFrame(ctk.CTkFrame):
    """Main application frame for subtitle management."""

    def __init__(self, master, plex, on_logout, current_log_file):
        super().__init__(master, fg_color="transparent")
        self.plex = plex
        self.on_logout = on_logout
        self.current_log_file = current_log_file
        self.libraries = []
        self.selected_items = []  # Items selected for subtitle management
        self.current_library = None
        self._is_destroyed = False
        self.top_level_frames = []  # Store only top-level show/movie frames for filtering
        self.search_text = ctk.StringVar()
        self.search_debounce_timer = None  # Timer for debouncing search
        self.search_text.trace_add("write", lambda *args: self.debounced_filter_items())
        self.subtitle_status_cache = {}  # Cache subtitle status: {item_id: has_subs}
        self.subtitle_status_filter = "all"  # Filter: "all", "missing", "has"
        self.all_movies = None  # Store all movies for filtering
        self.all_shows = None  # Store all shows for filtering

        # Initialize configuration manager
        self.config_manager = ConfigManager()

        # Load settings
        self.load_settings()

        # Initialize subtitle operations handler
        self.subtitle_ops = SubtitleOperations(self)

        # Configure subliminal cache (based on rustitles approach)
        try:
            # Set UTF-8 encoding for Python I/O
            if sys.platform.startswith('win'):
                os.environ['PYTHONIOENCODING'] = 'utf-8'

            # Configure cache directory
            cache_dir = os.path.join(tempfile.gettempdir(), 'plexsubsetter_cache')
            os.makedirs(cache_dir, exist_ok=True)

            # Use memory backend on Windows to avoid DBM issues
            if sys.platform.startswith('win'):
                region.configure('dogpile.cache.memory', replace_existing_backend=True)
            else:
                cache_file = os.path.join(cache_dir, 'cachefile.dbm')
                region.configure('dogpile.cache.dbm', arguments={'filename': cache_file}, replace_existing_backend=True)
        except (RuntimeError, ValueError, Exception) as e:
            # Cache already configured or configuration error
            logging.debug(f"Subliminal cache configuration skipped: {e}")

        # Configure grid - two column layout
        self.grid_columnconfigure(0, weight=0, minsize=380)  # Browser panel
        self.grid_columnconfigure(1, weight=1)  # Main content
        self.grid_rowconfigure(0, weight=1)

        self.create_widgets()
        self.refresh_libraries()

    def destroy(self):
        """Override destroy to set flag."""
        self._is_destroyed = True
        try:
            super().destroy()
        except (RuntimeError, AttributeError) as e:
            # Widget already destroyed or doesn't exist
            logging.debug(f"Error during widget destroy: {e}")

    @property
    def search_results(self):
        """Delegate search_results access to SubtitleOperations."""
        return self.subtitle_ops.search_results

    @property
    def subtitle_selections(self):
        """Delegate subtitle_selections access to SubtitleOperations."""
        return self.subtitle_ops.subtitle_selections

    def safe_after(self, ms, func):
        """Safely schedule a function call, checking if widget is destroyed."""
        if not self._is_destroyed:
            try:
                # Check if the widget still exists before scheduling
                if self.winfo_exists():
                    self.after(ms, func)
            except (RuntimeError, AttributeError, TclError) as e:
                # Widget destroyed or Tcl error during scheduling
                logging.debug(f"Could not schedule after() call: {e}")

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
        except (AttributeError, TclError) as e:
            logging.debug(f"Could not make combobox clickable: {e}")

    def create_widgets(self):
        """Create main application widgets."""

        # === LEFT PANEL: BROWSER ===
        browser_panel = ctk.CTkFrame(self, width=400)
        browser_panel.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        browser_panel.grid_columnconfigure(0, weight=1)
        browser_panel.grid_rowconfigure(5, weight=1)  # Browser scroll can expand
        browser_panel.grid_propagate(False)  # Prevent content from resizing the panel

        # Browser header
        ctk.CTkLabel(browser_panel, text="📚 Library Browser",
                    font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        # Library selection
        lib_select_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        lib_select_frame.grid(row=1, column=0, padx=15, pady=(10, 10), sticky="ew")
        lib_select_frame.grid_columnconfigure(0, weight=1)

        self.library_combo = ctk.CTkComboBox(lib_select_frame, values=["Loading..."],
                                            command=self.on_library_change, state="readonly")
        self.library_combo.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.make_combobox_clickable(self.library_combo)

        self.refresh_browser_btn = ctk.CTkButton(lib_select_frame, text="🔄 Reload Library",
                                                command=self.load_library_content, height=28)
        self.refresh_browser_btn.grid(row=1, column=0, sticky="ew")

        # Search/Filter bar (always visible)
        search_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        search_frame.grid(row=2, column=0, padx=15, pady=(5, 5), sticky="ew")
        search_frame.grid_columnconfigure(1, weight=1)

        # Search label
        ctk.CTkLabel(search_frame, text="Search:", font=ctk.CTkFont(size=12),
                    text_color=("gray30", "gray70")).grid(row=0, column=0, padx=(0, 8))

        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Type to filter by title...",
                                         placeholder_text_color=("gray60", "gray70"),
                                         textvariable=self.search_text, height=32,
                                         font=ctk.CTkFont(size=13))
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))

        clear_search_btn = ctk.CTkButton(search_frame, text="✕", width=32, height=32,
                                        command=self.clear_search,
                                        fg_color="transparent", hover_color=("gray80", "#404040"),
                                        text_color=("gray10", "gray90"))
        clear_search_btn.grid(row=0, column=2)

        # Subtitle status filter buttons (for movies only)
        self.filter_btn_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        self.filter_btn_frame.grid(row=3, column=0, padx=15, pady=(0, 5), sticky="ew")
        self.filter_btn_frame.grid_columnconfigure(0, weight=1)
        self.filter_btn_frame.grid_columnconfigure(1, weight=1)
        self.filter_btn_frame.grid_columnconfigure(2, weight=1)

        self.filter_all_btn = ctk.CTkButton(self.filter_btn_frame, text="All",
                                           command=lambda: self.set_subtitle_filter("all"),
                                           height=24)
        self.filter_all_btn.grid(row=0, column=0, padx=(0, 3), sticky="ew")

        self.filter_missing_btn = ctk.CTkButton(self.filter_btn_frame, text="Missing",
                                               command=lambda: self.set_subtitle_filter("missing"),
                                               height=24, fg_color="transparent", border_width=1,
                                               border_color=("gray60", "gray40"),
                                               text_color=("gray10", "gray90"))
        self.filter_missing_btn.grid(row=0, column=1, padx=(0, 3), sticky="ew")

        self.filter_has_btn = ctk.CTkButton(self.filter_btn_frame, text="Has Subs",
                                           command=lambda: self.set_subtitle_filter("has"),
                                           height=24, fg_color="transparent", border_width=1,
                                           border_color=("gray60", "gray40"),
                                           text_color=("gray10", "gray90"))
        self.filter_has_btn.grid(row=0, column=2, sticky="ew")

        # Hide filter buttons by default (will show for movies only)
        self.filter_btn_frame.grid_remove()

        # Filter status label (shows filter results count)
        self.filter_status_label = ctk.CTkLabel(browser_panel, text="",
                                               font=ctk.CTkFont(size=10), text_color="gray")
        self.filter_status_label.grid(row=4, column=0, padx=15, pady=(0, 5), sticky="w")

        # Browser scrollable frame
        self.browser_scroll = ctk.CTkScrollableFrame(browser_panel, label_text="Select Items")
        self.browser_scroll.grid(row=5, column=0, padx=15, pady=(5, 5), sticky="nsew")
        self.browser_scroll.grid_columnconfigure(0, weight=1)

        # Pagination controls (fixed position, outside scroll area)
        self.pagination_frame = ctk.CTkFrame(browser_panel, fg_color="transparent", height=40)
        self.pagination_frame.grid(row=6, column=0, padx=15, pady=(0, 5), sticky="ew")
        self.pagination_frame.grid_columnconfigure(1, weight=1)
        self.pagination_frame.grid_remove()  # Hidden by default

        # Selection info and controls
        select_control_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        select_control_frame.grid(row=7, column=0, padx=15, pady=(0, 15), sticky="ew")
        select_control_frame.grid_columnconfigure(0, weight=1)

        self.selection_label = ctk.CTkLabel(select_control_frame, text="0 items selected",
                                           font=ctk.CTkFont(size=11), text_color="gray")
        self.selection_label.grid(row=0, column=0, sticky="w", pady=(0, 5))

        btn_frame = ctk.CTkFrame(select_control_frame, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        self.select_all_btn = ctk.CTkButton(btn_frame, text="Select All", height=24,
                                           command=self.select_all_items,
                                           fg_color="transparent", border_width=1,
                                           text_color=("gray10", "gray90"))
        self.select_all_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.clear_selection_btn = ctk.CTkButton(btn_frame, text="Clear", height=24,
                                                command=self.clear_selection,
                                                fg_color="transparent", border_width=1,
                                                text_color=("gray10", "gray90"))
        self.clear_selection_btn.grid(row=0, column=1, sticky="ew")

        # === RIGHT PANEL: CONTROLS AND LOG ===
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(3, weight=1)  # Info panel can expand
        right_panel.grid_rowconfigure(5, weight=1)  # Log container can expand

        # === HEADER ===
        header_frame = ctk.CTkFrame(right_panel)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(header_frame, text=f"📺 {self.plex.friendlyName}",
                            font=ctk.CTkFont(size=24, weight="bold"))
        title.grid(row=0, column=0, sticky="w", padx=15, pady=15)

        settings_btn = ctk.CTkButton(header_frame, text="⚙ Settings", command=self.open_settings,
                                    width=100, fg_color="transparent", border_width=2,
                                    text_color=("gray10", "gray90"))
        settings_btn.grid(row=0, column=1, padx=(15, 5), pady=15)

        logout_btn = ctk.CTkButton(header_frame, text="Change Server", command=self.on_logout,
                                   width=120, fg_color="transparent", border_width=2,
                                   text_color=("gray10", "gray90"))
        logout_btn.grid(row=0, column=2, padx=(5, 15), pady=15)

        # === SUBTITLE OPTIONS ===
        options_frame = ctk.CTkFrame(right_panel)
        options_frame.grid(row=1, column=0, sticky="ew", pady=10)
        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=1)

        # Left column - Search language
        left_col = ctk.CTkFrame(options_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, padx=(15, 10), pady=15, sticky="new")

        ctk.CTkLabel(left_col, text="Search Language:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.search_lang_combo = ctk.CTkComboBox(left_col, values=list(SEARCH_LANGUAGES.keys()),
                                                 state="readonly", height=32)
        self.search_lang_combo.set("English")
        self.search_lang_combo.pack(fill="x", pady=(0, 10))
        self.make_combobox_clickable(self.search_lang_combo)

        # Checkboxes
        checkbox_frame = ctk.CTkFrame(left_col, fg_color="transparent")
        checkbox_frame.pack(fill="x")

        self.sdh_var = ctk.BooleanVar()
        self.sdh_check = ctk.CTkCheckBox(checkbox_frame, text="SDH",
                                        variable=self.sdh_var)
        self.sdh_check.pack(side="left", padx=(0, 15))

        self.forced_var = ctk.BooleanVar()
        self.forced_check = ctk.CTkCheckBox(checkbox_frame, text="Forced",
                                           variable=self.forced_var)
        self.forced_check.pack(side="left")

        # Right column - (removed Set Language dropdown)

        # Provider selection (spanning both columns)
        provider_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        provider_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="ew")

        ctk.CTkLabel(provider_frame, text="Subtitle Provider:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.provider_combo = ctk.CTkComboBox(provider_frame, values=list(SUBTITLE_PROVIDERS.keys()),
                                             state="readonly", height=32)
        self.provider_combo.set("OpenSubtitles")
        self.provider_combo.pack(fill="x", pady=(0, 0))
        self.make_combobox_clickable(self.provider_combo)

        # === ACTION BUTTONS ===
        actions_frame = ctk.CTkFrame(right_panel)
        actions_frame.grid(row=2, column=0, sticky="ew", pady=10)

        for i in range(3):
            actions_frame.grid_columnconfigure(i, weight=1)

        self.search_btn = ctk.CTkButton(actions_frame, text="🔍 Search Available",
                                       command=self.search_subtitles, height=40,
                                       state="disabled")
        self.search_btn.grid(row=0, column=0, padx=5, pady=15, sticky="ew")

        self.download_btn = ctk.CTkButton(actions_frame, text="⬇ Download Selected",
                                         command=self.download_subtitles, height=40,
                                         state="disabled")
        self.download_btn.grid(row=0, column=1, padx=5, pady=15, sticky="ew")

        self.list_btn = ctk.CTkButton(actions_frame, text="📋 List Current",
                                     command=self.list_subtitles, height=40,
                                     state="disabled")
        self.list_btn.grid(row=0, column=2, padx=5, pady=15, sticky="ew")

        # Second row for dry run and delete buttons
        self.dry_run_btn = ctk.CTkButton(actions_frame, text="👁 Dry Run (Preview Missing)",
                                        command=self.dry_run_missing_subtitles, height=40,
                                        fg_color=("green", "#2d7a2d"),
                                        hover_color=("darkgreen", "#236123"),
                                        state="disabled")
        self.dry_run_btn.grid(row=1, column=0, columnspan=2, padx=5, pady=(0, 15), sticky="ew")

        self.delete_subs_btn = ctk.CTkButton(actions_frame, text="🗑 Delete",
                                             command=self.delete_subtitles, height=40,
                                             fg_color=("red", "#8b0000"),
                                             hover_color=("darkred", "#6b0000"),
                                             state="disabled")
        self.delete_subs_btn.grid(row=1, column=2, padx=5, pady=(0, 15), sticky="ew")

        # === INFO PANEL (multi-purpose: subtitle selection, current subs, results) ===
        self.info_frame = ctk.CTkFrame(right_panel)
        self.info_frame.grid(row=3, column=0, sticky="nsew", pady=10)
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.info_frame.grid_rowconfigure(1, weight=1)
        self.info_frame.grid_remove()  # Hidden by default

        info_header = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        info_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        info_header.grid_columnconfigure(0, weight=1)

        self.info_panel_title = ctk.CTkLabel(info_header, text="📝 Information",
                    font=ctk.CTkFont(weight="bold", size=14))
        self.info_panel_title.grid(row=0, column=0, sticky="w")

        self.info_panel_action_btn = ctk.CTkButton(info_header, text="Clear",
                                           command=self.clear_info_panel,
                                           width=120, height=24)
        self.info_panel_action_btn.grid(row=0, column=1, sticky="e")

        # Scrollable area for content
        self.info_scroll = ctk.CTkScrollableFrame(self.info_frame, height=250,
                                                       fg_color="transparent")
        self.info_scroll.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        self.info_scroll.grid_columnconfigure(0, weight=1)

        # === STATUS BAR ===
        status_frame = ctk.CTkFrame(right_panel, fg_color=("gray85", "gray20"), height=30)
        status_frame.grid(row=4, column=0, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_propagate(False)

        self.status_label = ctk.CTkLabel(status_frame, text="Ready",
                                         font=ctk.CTkFont(size=11),
                                         anchor="w")
        self.status_label.pack(side="left", padx=15, pady=5)

        # === OUTPUT LOG (Smaller, collapsible) ===
        self.log_container = ctk.CTkFrame(right_panel)
        self.log_container.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
        self.log_container.grid_columnconfigure(0, weight=1)
        self.log_container.grid_rowconfigure(1, weight=1)  # Log text frame can expand

        log_header = ctk.CTkFrame(self.log_container, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 5))
        log_header.grid_columnconfigure(1, weight=1)

        self.log_toggle_btn = ctk.CTkButton(log_header, text="▼ Log", command=self.toggle_log,
                                           width=80, height=24, fg_color="transparent",
                                           border_width=1, anchor="w",
                                           text_color=("gray10", "gray90"))
        self.log_toggle_btn.grid(row=0, column=0, sticky="w")

        # Log file path label
        log_file_label = ctk.CTkLabel(log_header, text=f"📄 Log file: {self.current_log_file}",
                                      font=ctk.CTkFont(size=10), text_color="gray")
        log_file_label.grid(row=0, column=1, sticky="w", padx=10)

        clear_btn = ctk.CTkButton(log_header, text="Clear", command=self.clear_log,
                                 width=60, height=24, fg_color="transparent",
                                 text_color=("gray10", "gray90"))
        clear_btn.grid(row=0, column=2, sticky="e")

        # Text widget with proper wrapping (smaller)
        self.log_text_frame = ctk.CTkFrame(self.log_container)
        self.log_text_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        self.log_text_frame.grid_columnconfigure(0, weight=1)
        self.log_text_frame.grid_rowconfigure(0, weight=1)
        self.log_text_frame.grid_remove()  # Start collapsed

        self.output_text = ctk.CTkTextbox(self.log_text_frame, wrap="word",
                                          font=ctk.CTkFont(size=11))
        self.output_text.pack(fill="both", expand=True, padx=2, pady=2)

        # === PROGRESS BAR ===
        self.progress_bar = ctk.CTkProgressBar(right_panel, mode="indeterminate")
        self.progress_bar.grid(row=6, column=0, sticky="ew", pady=(0, 0))
        self.progress_bar.grid_remove()

        # Initialize library browser handler
        self.library_browser = LibraryBrowser(self, self.browser_scroll)

    def log(self, message, level="info"):
        """Add message to log and write to file.

        Args:
            message (str): Message to log
            level (str): Log level - "info", "warning", "error", "debug"
        """
        # Write to GUI log
        self.output_text.configure(state="normal")
        self.output_text.insert("end", message + "\n")
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

        # Write to file log based on level
        if level == "error":
            logging.error(message)
        elif level == "warning":
            logging.warning(message)
        elif level == "debug":
            logging.debug(message)
        else:
            logging.info(message)

    def clear_log(self):
        """Clear the output log."""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

    def toggle_log(self):
        """Toggle log visibility."""
        if self.log_text_frame.winfo_viewable():
            self.log_text_frame.grid_remove()
            self.log_toggle_btn.configure(text="▶ Log")
        else:
            self.log_text_frame.grid()
            self.log_toggle_btn.configure(text="▼ Log")

    def update_status(self, message):
        """Update status bar message."""
        self.status_label.configure(text=message)

    def clear_info_panel(self):
        """Clear the info panel."""
        for widget in self.info_scroll.winfo_children():
            widget.destroy()
        self.subtitle_selections.clear()
        self.info_frame.grid_remove()
        self.update_status("Ready")

    def refresh_libraries(self):
        """Refresh library list with error handling."""
        self.log("Fetching libraries...")

        @retry_with_backoff(max_attempts=DEFAULT_RETRY_ATTEMPTS, initial_delay=DEFAULT_RETRY_DELAY, exceptions=(Exception,))
        def fetch_libraries():
            """Fetch libraries with retry."""
            if self._is_destroyed:
                return []

            try:
                libraries = []
                for section in self.plex.library.sections():
                    libraries.append(section)
                return libraries
            except ConnectionError as e:
                raise PlexConnectionError(original_error=e)
            except Exception as e:
                if "unauthorized" in str(e).lower():
                    raise PlexAuthenticationError(e)
                raise

        def refresh_thread():
            try:
                with ErrorContext("library refresh", get_crash_reporter()):
                    self.libraries = fetch_libraries()

                    # Log found libraries
                    for section in self.libraries:
                        self.safe_after(0, lambda s=section: self.log(f"  Found: {s.title} (Type: {s.type})"))

                    lib_names = [lib.title for lib in self.libraries]
                    self.safe_after(0, lambda: self.library_combo.configure(values=lib_names))

                    if lib_names:
                        self.safe_after(0, lambda: self.library_combo.set("Select a library..."))
                        # Don't auto-load library - let user choose
                        self.safe_after(0, lambda: self.log(f"[OK] Loaded {len(self.libraries)} libraries - Select one to begin\n"))
                    else:
                        self.safe_after(0, lambda: self.log("[!] No libraries found\n", level="warning"))

            except (PlexConnectionError, PlexAuthenticationError) as e:
                error_msg = str(e)
                logging.error(error_msg)
                self.safe_after(0, lambda: self.log(f"✗ {error_msg}\n", level="error"))
                self.safe_after(0, lambda: self.update_status("Failed to load libraries - check connection"))
            except Exception as e:
                error_msg = f"Unexpected error fetching libraries: {e}"
                logging.error(error_msg)
                get_crash_reporter().report_crash(e, {"action": "refresh_libraries"})
                self.safe_after(0, lambda: self.log(f"✗ {error_msg}\n", level="error"))

        threading.Thread(target=refresh_thread, daemon=True).start()

    def on_library_change(self, choice):
        """Handle library selection change."""
        self.load_library_content()

    def show_browser_loading(self):
        """Show loading indicator in browser."""
        # Clear browser
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()

        # Create loading frame
        loading_frame = ctk.CTkFrame(self.browser_scroll, fg_color="transparent")
        loading_frame.pack(expand=True, fill="both", pady=50)

        # Loading spinner (animated dots)
        self.loading_label = ctk.CTkLabel(loading_frame, text="Loading library...",
                                         font=ctk.CTkFont(size=14),
                                         text_color="gray")
        self.loading_label.pack(pady=(20, 10))

        # Progress bar
        self.browser_progress = ctk.CTkProgressBar(loading_frame, mode="indeterminate", width=200)
        self.browser_progress.pack(pady=10)
        self.browser_progress.start()

    def hide_browser_loading(self):
        """Hide loading indicator in browser."""
        if hasattr(self, 'browser_progress'):
            self.browser_progress.stop()

    def clear_search(self):
        """Clear the search filter - delegated to LibraryBrowser."""
        self.library_browser.clear_search()

    def set_subtitle_filter(self, filter_type):
        """Set the subtitle status filter (all, missing, has) - delegated to LibraryBrowser."""
        self.library_browser.set_subtitle_filter(filter_type)

    def debounced_filter_items(self):
        """Debounce search filter to avoid filtering on every keystroke."""
        # Cancel previous timer
        if self.search_debounce_timer is not None:
            try:
                self.after_cancel(self.search_debounce_timer)
            except Exception:
                pass

        # Schedule new filter after 300ms delay
        self.search_debounce_timer = self.after(300, self.filter_items)

    def filter_items(self):
        """Filter items based on search text and subtitle status - delegated to LibraryBrowser."""
        self.library_browser.filter_items()

    def apply_subtitle_status_filter(self):
        """Apply subtitle status filter to currently displayed movie items - delegated to LibraryBrowser."""
        self.library_browser.apply_subtitle_status_filter()

    def _show_has_loaded_episodes_matching_filter(self, show_frame, looking_for_has_subs):
        """Check if a show has any LOADED episodes matching the subtitle filter.

        This only checks episodes that have already been loaded into the UI,
        preventing the need to load all episodes just for filtering.
        """
        # Recursively search through the show frame for episode items
        def search_episodes(widget):
            # Check if this widget has an item_obj
            if hasattr(widget, 'item_obj'):
                item = widget.item_obj
                if isinstance(item, Episode):
                    has_subs = self.check_has_subtitles(item)
                    if has_subs == looking_for_has_subs:
                        return True

            # Search children
            try:
                for child in widget.winfo_children():
                    if search_episodes(child):
                        return True
            except (RuntimeError, TclError) as e:
                # Widget destroyed during iteration
                logging.debug(f"Error searching widget children: {e}")

            return False

        # If no loaded episodes found matching filter, but show is expanded,
        # check if there are ANY loaded episodes at all
        result = search_episodes(show_frame)

        # If we found no matches but the show is expanded, only show if there are NO episodes loaded yet
        # (meaning seasons haven't been expanded, so we don't know)
        if not result:
            # Check if any episodes are actually loaded
            def has_any_episodes(widget):
                if hasattr(widget, 'item_obj') and isinstance(widget.item_obj, Episode):
                    return True
                try:
                    for child in widget.winfo_children():
                        if has_any_episodes(child):
                            return True
                except (RuntimeError, TclError) as e:
                    # Widget destroyed during iteration
                    logging.debug(f"Error checking for episodes: {e}")
                return False

            # If no episodes loaded yet, show the item (we don't know)
            if not has_any_episodes(show_frame):
                return True

        return result

    def load_library_content(self):
        """Load content from selected library into browser - delegated to LibraryBrowser."""
        self.library_browser.load_library_content()

    def truncate_title(self, title, max_length=80):
        """Truncate title if too long - delegated to LibraryBrowser."""
        return self.library_browser.truncate_title(title, max_length)

    def populate_movies(self, movies):
        """Populate browser with movies with page navigation - delegated to LibraryBrowser."""
        self.library_browser.populate_movies(movies)

    def populate_shows(self, shows):
        """Populate browser with shows (expandable) with page navigation - delegated to LibraryBrowser."""
        self.library_browser.populate_shows(shows)

    def toggle_show(self, show, frame, expand_var):
        """Toggle show expansion to show seasons/episodes - delegated to LibraryBrowser."""
        self.library_browser.toggle_show(show, frame, expand_var)

    def populate_seasons(self, show_frame, seasons):
        """Populate seasons under a show - delegated to LibraryBrowser."""
        self.library_browser.populate_seasons(show_frame, seasons)

    def toggle_season(self, season, frame, expand_var):
        """Toggle season expansion to show episodes - delegated to LibraryBrowser."""
        self.library_browser.toggle_season(season, frame, expand_var)

    def populate_episodes(self, season_frame, episodes):
        """Populate episodes under a season with page navigation - delegated to LibraryBrowser."""
        self.library_browser.populate_episodes(season_frame, episodes)

    def on_item_selected(self, item, var):
        """Handle individual item (movie/episode) selection - delegated to LibraryBrowser."""
        self.library_browser.on_item_selected(item, var)

    def on_show_selected(self, show, var, show_frame):
        """Handle show selection (selects all episodes) - delegated to LibraryBrowser."""
        self.library_browser.on_show_selected(show, var, show_frame)

    def on_season_selected(self, season, var, season_frame):
        """Handle season selection (selects all episodes in season) - delegated to LibraryBrowser."""
        self.library_browser.on_season_selected(season, var, season_frame)

    def select_all_items(self):
        """Select all items in current library - delegated to LibraryBrowser."""
        self.library_browser.select_all_items()

    def clear_selection(self):
        """Clear all selections - delegated to LibraryBrowser."""
        self.library_browser.clear_selection()

    def update_selection_label(self):
        """Update selection count label - delegated to LibraryBrowser."""
        self.library_browser.update_selection_label()

    def show_subtitle_status(self, item):
        """Show current subtitle status for a video item - delegated to LibraryBrowser."""
        self.library_browser.show_subtitle_status(item)

    def check_has_subtitles(self, item, force_refresh=False):
        """Check if an item has subtitles (fast check, uses cache) - delegated to LibraryBrowser."""
        return self.library_browser.check_has_subtitles(item, force_refresh)

    def refresh_subtitle_indicators(self, items_to_refresh=None):
        """Refresh subtitle status indicators in the browser - delegated to LibraryBrowser."""
        self.library_browser.refresh_subtitle_indicators(items_to_refresh)

    def get_video_items(self):
        """Get selected video items."""
        return self.selected_items

    def populate_subtitle_selection_panel(self):
        """Populate the info panel with search results for subtitle selection - delegated to SubtitleOperations."""
        self.subtitle_ops.populate_subtitle_selection_panel()

    def search_subtitles(self):
        """Search for available subtitles (does not download) - delegated to SubtitleOperations."""
        self.subtitle_ops.search_subtitles()

    def download_subtitles(self):
        """Download selected subtitles from search results - delegated to SubtitleOperations."""
        self.subtitle_ops.download_subtitles()

    def dry_run_missing_subtitles(self):
        """Preview which subtitles would be available for items missing them (no download) - delegated to SubtitleOperations."""
        self.subtitle_ops.dry_run_missing_subtitles()

    def display_dry_run_results(self, results, language_name, provider_name):
        """Display dry run results in info panel - delegated to SubtitleOperations."""
        self.subtitle_ops.display_dry_run_results(results, language_name, provider_name)

    def list_subtitles(self):
        """List available subtitles in info panel - delegated to SubtitleOperations."""
        self.subtitle_ops.list_subtitles()

    def delete_subtitles(self):
        """Delete all subtitle streams from selected items - delegated to SubtitleOperations."""
        self.subtitle_ops.delete_subtitles()

    def show_progress(self):
        """Show progress bar."""
        self.progress_bar.grid()
        self.progress_bar.start()

    def hide_progress(self):
        """Hide progress bar."""
        self.progress_bar.stop()
        self.progress_bar.grid_remove()

    def disable_action_buttons(self):
        """Disable action buttons."""
        self.search_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.list_btn.configure(state="disabled")
        self.dry_run_btn.configure(state="disabled")
        self.delete_subs_btn.configure(state="disabled")
        self.refresh_browser_btn.configure(state="disabled")

    def enable_action_buttons(self):
        """Enable action buttons if items selected."""
        state = "normal" if self.selected_items else "disabled"
        self.search_btn.configure(state=state)
        self.list_btn.configure(state=state)
        self.dry_run_btn.configure(state=state)
        self.delete_subs_btn.configure(state=state)

        # Download button only enabled if we have search results
        download_state = "normal" if self.search_results else "disabled"
        self.download_btn.configure(state=download_state)

        self.refresh_browser_btn.configure(state="normal")

    def _get_item_title(self, item):
        """Get formatted title."""
        if isinstance(item, Movie):
            return f"{item.title} ({item.year})"
        elif isinstance(item, Episode):
            return f"{item.grandparentTitle} S{item.seasonNumber:02d}E{item.index:02d} - {item.title}"
        else:
            return item.title

    def show_confirmation_dialog(self, title, message):
        """Show a confirmation dialog and return True if user confirms."""
        return messagebox.askyesno(title, message, parent=self)

    def load_settings(self):
        """Load application settings using ConfigManager."""
        settings = self.config_manager.load_settings()

        # Apply settings to instance variables
        self.subtitle_save_method = settings['subtitle_save_method']
        self.default_language = settings['default_language']
        self.appearance_mode = settings['appearance_mode']
        self.remember_last_library = settings['remember_last_library']
        self.last_library = settings['last_library']
        self.prefer_hearing_impaired = settings['prefer_hearing_impaired']
        self.prefer_forced = settings['prefer_forced']
        self.default_providers = settings['default_providers']
        self.search_timeout = settings['search_timeout']
        self.show_log_on_startup = settings['show_log_on_startup']
        self.default_subtitle_filter = settings['default_subtitle_filter']
        self.confirm_batch_operations = settings['confirm_batch_operations']
        self.batch_operation_threshold = settings['batch_operation_threshold']
        self.concurrent_downloads = settings['concurrent_downloads']
        self.enable_debug_logging = settings['enable_debug_logging']

        # Apply runtime settings
        ctk.set_appearance_mode(self.appearance_mode)

        # Set logging level based on debug setting
        if self.enable_debug_logging:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

    def save_settings(self):
        """Save application settings using ConfigManager."""
        # Gather current settings
        settings = {
            'subtitle_save_method': self.subtitle_save_method,
            'default_language': self.default_language,
            'appearance_mode': self.appearance_mode,
            'remember_last_library': self.remember_last_library,
            'last_library': self.last_library if hasattr(self, 'last_library') else '',
            'prefer_hearing_impaired': self.prefer_hearing_impaired,
            'prefer_forced': self.prefer_forced,
            'default_providers': self.default_providers,
            'search_timeout': self.search_timeout,
            'show_log_on_startup': self.show_log_on_startup,
            'default_subtitle_filter': self.default_subtitle_filter,
            'confirm_batch_operations': self.confirm_batch_operations,
            'batch_operation_threshold': self.batch_operation_threshold,
            'concurrent_downloads': self.concurrent_downloads,
            'enable_debug_logging': self.enable_debug_logging
        }

        # Save using ConfigManager
        self.config_manager.save_settings(settings)

        # Apply runtime settings changes
        ctk.set_appearance_mode(self.appearance_mode)
        if self.enable_debug_logging:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

    def open_settings(self):
        """Open comprehensive settings dialog with tabs."""
        # Gather current settings
        current_settings = {
            'subtitle_save_method': self.subtitle_save_method,
            'default_language': self.default_language,
            'appearance_mode': self.appearance_mode,
            'remember_last_library': self.remember_last_library,
            'prefer_hearing_impaired': self.prefer_hearing_impaired,
            'prefer_forced': self.prefer_forced,
            'default_providers': self.default_providers,
            'search_timeout': self.search_timeout,
            'show_log_on_startup': self.show_log_on_startup,
            'default_subtitle_filter': self.default_subtitle_filter,
            'confirm_batch_operations': self.confirm_batch_operations,
            'batch_operation_threshold': self.batch_operation_threshold,
            'concurrent_downloads': self.concurrent_downloads,
            'enable_debug_logging': self.enable_debug_logging,
        }

        # Create and show dialog
        dialog = SettingsDialog(
            parent=self,
            current_settings=current_settings,
            on_save_callback=self._apply_settings,
            log_file_path=self.current_log_file
        )
        dialog.show()

    def _apply_settings(self, updated_settings):
        """Apply settings from dialog.

        Args:
            updated_settings: Dict of updated setting values
        """
        # Apply all settings
        self.subtitle_save_method = updated_settings['subtitle_save_method']
        self.default_language = updated_settings['default_language']
        self.appearance_mode = updated_settings['appearance_mode']
        self.remember_last_library = updated_settings['remember_last_library']
        self.prefer_hearing_impaired = updated_settings['prefer_hearing_impaired']
        self.prefer_forced = updated_settings['prefer_forced']
        self.default_providers = updated_settings['default_providers']
        self.search_timeout = updated_settings['search_timeout']
        self.show_log_on_startup = updated_settings['show_log_on_startup']
        self.default_subtitle_filter = updated_settings['default_subtitle_filter']
        self.confirm_batch_operations = updated_settings['confirm_batch_operations']
        self.batch_operation_threshold = updated_settings['batch_operation_threshold']
        self.concurrent_downloads = updated_settings['concurrent_downloads']
        self.enable_debug_logging = updated_settings['enable_debug_logging']

        # Save to config file
        self.save_settings()

        # Update UI
        self.update_status("Settings saved successfully")
        self.log("Settings saved and applied")
