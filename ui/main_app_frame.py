"""
Main application frame for subtitle management.

This module contains the MainAppFrame class which provides the primary UI
for managing subtitles in Plex libraries, including search, download, set,
upload, and delete operations.
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading
import configparser
import os
import sys
import tempfile
import logging
from plexapi.video import Movie, Episode, Show, Season
from subliminal import region, download_subtitles
from subliminal.video import Episode as SubliminalEpisode, Movie as SubliminalMovie
from babelfish import Language
from error_handling import (
    retry_with_backoff,
    ErrorMessageFormatter,
    get_crash_reporter,
    ErrorContext,
    PlexConnectionError,
    PlexAuthenticationError
)
from utils.constants import SEARCH_LANGUAGES, SUBTITLE_PROVIDERS


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
        self.search_text.trace_add("write", lambda *args: self.filter_items())
        self.search_results = {}  # Store search results: {item: [subtitles]}
        self.subtitle_status_cache = {}  # Cache subtitle status: {item_id: has_subs}
        self.subtitle_status_filter = "all"  # Filter: "all", "missing", "has"
        self.all_movies = None  # Store all movies for filtering
        self.all_shows = None  # Store all shows for filtering

        # Load settings
        self.load_settings()

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
                region.configure('dogpile.cache.memory')
            else:
                cache_file = os.path.join(cache_dir, 'cachefile.dbm')
                region.configure('dogpile.cache.dbm', arguments={'filename': cache_file})
        except:
            pass  # Cache already configured

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
        except:
            pass

    def safe_after(self, ms, func):
        """Safely schedule a function call, checking if widget is destroyed."""
        if not self._is_destroyed:
            try:
                # Check if the widget still exists before scheduling
                if self.winfo_exists():
                    self.after(ms, func)
            except:
                pass

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

        self.refresh_browser_btn = ctk.CTkButton(lib_select_frame, text="🔄 Reload Library",
                                                command=self.load_library_content, height=28)
        self.refresh_browser_btn.grid(row=1, column=0, sticky="ew")

        # Search/Filter bar (always visible)
        search_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        search_frame.grid(row=2, column=0, padx=15, pady=(5, 5), sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="🔍 Search/filter items...",
                                         textvariable=self.search_text, height=32)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        clear_search_btn = ctk.CTkButton(search_frame, text="✕", width=32, height=32,
                                        command=self.clear_search,
                                        fg_color="transparent", hover_color=("gray80", "#404040"),
                                        text_color=("gray10", "gray90"))
        clear_search_btn.grid(row=0, column=1)

        # Subtitle status filter buttons (for movies only)
        self.filter_btn_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        self.filter_btn_frame.grid(row=3, column=0, padx=15, pady=(0, 5), sticky="ew")
        self.filter_btn_frame.grid_columnconfigure(0, weight=1)
        self.filter_btn_frame.grid_columnconfigure(1, weight=1)
        self.filter_btn_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(self.filter_btn_frame, text="Show:", font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="gray").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 3))

        self.filter_all_btn = ctk.CTkButton(self.filter_btn_frame, text="All",
                                           command=lambda: self.set_subtitle_filter("all"),
                                           height=24)
        self.filter_all_btn.grid(row=1, column=0, padx=(0, 3), sticky="ew")

        self.filter_missing_btn = ctk.CTkButton(self.filter_btn_frame, text="Missing",
                                               command=lambda: self.set_subtitle_filter("missing"),
                                               height=24, fg_color="transparent", border_width=1,
                                               border_color=("gray60", "gray40"),
                                               text_color=("gray10", "gray90"))
        self.filter_missing_btn.grid(row=1, column=1, padx=(0, 3), sticky="ew")

        self.filter_has_btn = ctk.CTkButton(self.filter_btn_frame, text="Has Subs",
                                           command=lambda: self.set_subtitle_filter("has"),
                                           height=24, fg_color="transparent", border_width=1,
                                           border_color=("gray60", "gray40"),
                                           text_color=("gray10", "gray90"))
        self.filter_has_btn.grid(row=1, column=2, sticky="ew")

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

        # Store selection variables
        self.subtitle_selections = {}  # {item: IntVar for selected subtitle index}

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

        @retry_with_backoff(max_attempts=2, initial_delay=2.0, exceptions=(Exception,))
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
                        self.safe_after(0, lambda: self.log(f"✓ Loaded {len(self.libraries)} libraries - Select one to begin\n"))
                    else:
                        self.safe_after(0, lambda: self.log("⚠ No libraries found\n", level="warning"))

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
        """Clear the search filter."""
        self.search_text.set("")
        self.filter_status_label.configure(text="")

    def set_subtitle_filter(self, filter_type):
        """Set the subtitle status filter (all, missing, has)."""
        self.subtitle_status_filter = filter_type

        # Update button appearances to show active filter
        if filter_type == "all":
            self.filter_all_btn.configure(fg_color=("blue", "#1f538d"), border_width=0)
            self.filter_missing_btn.configure(fg_color="transparent", border_width=1)
            self.filter_has_btn.configure(fg_color="transparent", border_width=1)
        elif filter_type == "missing":
            self.filter_all_btn.configure(fg_color="transparent", border_width=1)
            self.filter_missing_btn.configure(fg_color=("red", "#8b0000"), border_width=0)
            self.filter_has_btn.configure(fg_color="transparent", border_width=1)
        elif filter_type == "has":
            self.filter_all_btn.configure(fg_color="transparent", border_width=1)
            self.filter_missing_btn.configure(fg_color="transparent", border_width=1)
            self.filter_has_btn.configure(fg_color=("green", "#2d7a2d"), border_width=0)

        # Reapply filter
        self.filter_items()

    def filter_items(self):
        """Filter items based on search text and subtitle status."""
        # If we have movies or shows loaded, reload the page to apply search filter
        if hasattr(self, 'all_movies') and self.all_movies is not None:
            # Reload page 1 with new search filter
            if hasattr(self, 'load_movie_page'):
                self.load_movie_page(1)
        elif hasattr(self, 'all_shows') and self.all_shows is not None:
            # Reload page 1 with new search filter
            if hasattr(self, 'load_show_page'):
                self.load_show_page(1)

        # Apply subtitle status filter to currently displayed items (for movies only)
        if self.subtitle_status_filter != "all":
            self.apply_subtitle_status_filter()

    def apply_subtitle_status_filter(self):
        """Apply subtitle status filter to currently displayed movie items."""
        subtitle_filter = self.subtitle_status_filter

        # Only apply subtitle filter to movies (not shows)
        if not hasattr(self, 'all_movies') or self.all_movies is None:
            # Clear filter status label for shows
            self.filter_status_label.configure(text="")
            return

        visible_count = 0
        total_count = len(self.top_level_frames)

        for frame in self.top_level_frames:
            match_found = False

            # Only filter movies (frames with item_obj but not show_obj)
            if hasattr(frame, 'item_obj') and not hasattr(frame, 'show_obj'):
                if subtitle_filter == "all":
                    match_found = True
                else:
                    item_obj = frame.item_obj
                    has_subs = self.check_has_subtitles(item_obj)
                    if subtitle_filter == "missing" and not has_subs:
                        match_found = True
                    elif subtitle_filter == "has" and has_subs:
                        match_found = True

            # Show or hide based on match
            if match_found:
                try:
                    frame.pack(fill="x", pady=2, padx=5)
                    visible_count += 1
                except:
                    pass
            else:
                try:
                    frame.pack_forget()
                except:
                    pass

        # Update filter status
        search_query = self.search_text.get().lower().strip()
        filter_text = ""
        if search_query:
            filter_text = f"Search: '{search_query}'"
        if subtitle_filter != "all":
            if filter_text:
                filter_text += " | "
            filter_text += f"Status: {subtitle_filter}"

        if visible_count != total_count or filter_text:
            self.filter_status_label.configure(
                text=f"Showing {visible_count} of {total_count} items" + (f" ({filter_text})" if filter_text else ""),
                text_color="#e5a00d"
            )
        else:
            self.filter_status_label.configure(text="")

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
            except:
                pass

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
                except:
                    pass
                return False

            # If no episodes loaded yet, show the item (we don't know)
            if not has_any_episodes(show_frame):
                return True

        return result

    def load_library_content(self):
        """Load content from selected library into browser."""
        library_name = self.library_combo.get()
        if not library_name or library_name == "Select a library...":
            return

        self.log(f"Loading {library_name}...")
        self.clear_selection()
        self.clear_search()  # Clear search filter when loading new library

        # Show loading indicator
        self.show_browser_loading()

        def load_thread():
            if self._is_destroyed:
                return

            try:
                self.current_library = next((lib for lib in self.libraries if lib.title == library_name), None)
                if not self.current_library:
                    self.safe_after(0, self.hide_browser_loading)
                    return

                if self.current_library.type == 'movie':
                    movies = self.current_library.all()
                    self.safe_after(0, lambda: self.hide_browser_loading())
                    self.safe_after(0, lambda: self.populate_movies(movies))
                elif self.current_library.type == 'show':
                    shows = self.current_library.all()
                    self.safe_after(0, lambda: self.hide_browser_loading())
                    self.safe_after(0, lambda: self.populate_shows(shows))

                self.safe_after(0, lambda: self.log(f"✓ Loaded {library_name}\n"))

            except Exception as e:
                self.safe_after(0, lambda: self.hide_browser_loading())
                self.safe_after(0, lambda err=str(e): self.log(f"✗ Error loading library: {err}\n", level="error"))

        threading.Thread(target=load_thread, daemon=True).start()

    def truncate_title(self, title, max_length=80):
        """Truncate title if too long."""
        if len(title) > max_length:
            return title[:max_length-3] + "..."
        return title

    def populate_movies(self, movies):
        """Populate browser with movies with page navigation."""
        # Clear any loading indicator
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()

        # Clear top-level frames list
        self.top_level_frames.clear()

        # Show filter buttons for movies
        self.filter_btn_frame.grid()
        # Reset filter to "all"
        self.set_subtitle_filter("all")

        # Store all movies (unfiltered) and clear shows
        self.all_movies = movies
        self.all_shows = None
        self.movies_per_page = 30
        self.current_movie_page = 1

        # Define the page loading function
        def load_movie_page(page_num):
            """Load a specific page of filtered movies."""
            # Apply search and filter to get filtered list
            search_query = self.search_text.get().lower().strip()
            filtered_movies = [m for m in self.all_movies
                             if not search_query or search_query in m.title.lower()]

            # Apply subtitle status filter (we'll filter after loading for performance)
            total_movies = len(filtered_movies)
            total_pages = max(1, (total_movies + self.movies_per_page - 1) // self.movies_per_page)

            if self._is_destroyed or page_num < 1 or page_num > total_pages:
                return

            # Clear current items
            for widget in self.browser_scroll.winfo_children():
                widget.destroy()
            self.top_level_frames.clear()

            self.current_movie_page = page_num

            # Calculate range
            start_idx = (page_num - 1) * self.movies_per_page
            end_idx = min(start_idx + self.movies_per_page, total_movies)

            # Create movie widgets for this page
            page_frames = []
            for i in range(start_idx, end_idx):
                movie = filtered_movies[i]
                var = ctk.BooleanVar()
                frame = ctk.CTkFrame(self.browser_scroll, fg_color="transparent")
                frame.pack(fill="x", pady=2, padx=5)

                status_label = ctk.CTkLabel(frame, text="○", width=20,
                                           text_color="gray", font=ctk.CTkFont(size=14, weight="bold"))
                status_label.pack(side="left", padx=(0, 5))

                title_text = self.truncate_title(f"{movie.title} ({movie.year})")
                cb = ctk.CTkCheckBox(frame, text=title_text,
                                    variable=var,
                                    command=lambda m=movie, v=var: self.on_item_selected(m, v))
                cb.pack(side="left", fill="x", expand=True)

                frame.status_label = status_label
                frame.item_obj = movie
                self.top_level_frames.append(frame)
                page_frames.append(frame)

            # Update external pagination controls
            for widget in self.pagination_frame.winfo_children():
                widget.destroy()

            prev_btn = ctk.CTkButton(self.pagination_frame, text="◀ Previous",
                                     width=100, height=32,
                                     command=lambda: load_movie_page(page_num - 1),
                                     state="normal" if page_num > 1 else "disabled")
            prev_btn.grid(row=0, column=0, padx=5)

            page_label = ctk.CTkLabel(self.pagination_frame,
                                     text=f"Page {page_num} of {total_pages}",
                                     font=ctk.CTkFont(size=12))
            page_label.grid(row=0, column=1, padx=5)

            next_btn = ctk.CTkButton(self.pagination_frame, text="Next ▶",
                                     width=100, height=32,
                                     command=lambda: load_movie_page(page_num + 1),
                                     state="normal" if page_num < total_pages else "disabled")
            next_btn.grid(row=0, column=2, padx=5)

            # Show pagination frame
            self.pagination_frame.grid()

            # Update status
            self.update_status(f"Page {page_num}/{total_pages} ({start_idx + 1}-{end_idx} of {total_movies} movies)")

            # Load subtitle status in background
            def start_subtitle_status_loading():
                def load_subtitle_status():
                    if self._is_destroyed:
                        return
                    for frame in page_frames:
                        if self._is_destroyed:
                            return
                        try:
                            item = frame.item_obj
                            has_subs = self.check_has_subtitles(item)
                            status_icon = "✓" if has_subs else "✗"
                            status_color = ("green", "#2d7a2d") if has_subs else ("red", "#8b0000")

                            def update_status_label(frame_ref=frame, icon=status_icon, color=status_color):
                                try:
                                    # Check if widget still exists before updating
                                    if frame_ref.winfo_exists() and hasattr(frame_ref, 'status_label'):
                                        frame_ref.status_label.configure(text=icon, text_color=color)
                                except:
                                    pass

                            self.safe_after(0, update_status_label)
                        except:
                            pass
                    # Apply subtitle status filter after loading all statuses
                    if not self._is_destroyed:
                        self.safe_after(0, lambda: self.apply_subtitle_status_filter())
                threading.Thread(target=load_subtitle_status, daemon=True).start()

            self.after(50, start_subtitle_status_loading)

        # Store the load function so it can be called when filters change
        self.load_movie_page = load_movie_page

        # Load first page
        if movies:
            load_movie_page(1)
        else:
            self.pagination_frame.grid_remove()
            self.update_status("No movies found")

    def populate_shows(self, shows):
        """Populate browser with shows (expandable) with page navigation."""
        # Clear any loading indicator
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()

        # Clear top-level frames list
        self.top_level_frames.clear()

        # Hide filter buttons for TV shows
        self.filter_btn_frame.grid_remove()
        # Reset filter to "all"
        self.subtitle_status_filter = "all"
        # Clear filter status label (shows don't use subtitle status filter)
        self.filter_status_label.configure(text="")

        # Store all shows (unfiltered) and clear movies
        self.all_shows = shows
        self.all_movies = None
        self.shows_per_page = 25
        self.current_show_page = 1

        def load_show_page(page_num):
            """Load a specific page of filtered shows."""
            # Apply search filter to get filtered list
            search_query = self.search_text.get().lower().strip()
            filtered_shows = [s for s in self.all_shows
                            if not search_query or search_query in s.title.lower()]

            total_shows = len(filtered_shows)
            total_pages = max(1, (total_shows + self.shows_per_page - 1) // self.shows_per_page)

            if self._is_destroyed or page_num < 1 or page_num > total_pages:
                return

            # Clear current items
            for widget in self.browser_scroll.winfo_children():
                widget.destroy()
            self.top_level_frames.clear()

            self.current_show_page = page_num

            # Calculate range
            start_idx = (page_num - 1) * self.shows_per_page
            end_idx = min(start_idx + self.shows_per_page, total_shows)

            # Create show widgets for this page
            for i in range(start_idx, end_idx):
                show = filtered_shows[i]
                show_frame = ctk.CTkFrame(self.browser_scroll, fg_color="transparent")
                show_frame.pack(fill="x", pady=2, padx=5)

                show_inner = ctk.CTkFrame(show_frame, fg_color="transparent")
                show_inner.pack(fill="x")

                show_var = ctk.BooleanVar()
                expand_var = ctk.BooleanVar(value=False)

                expand_btn = ctk.CTkButton(show_inner, text="▶", width=30, height=24,
                                           fg_color="transparent",
                                           text_color=("gray10", "gray90"),
                                           command=lambda s=show, f=show_frame, v=expand_var: self.toggle_show(s, f, v))
                expand_btn.pack(side="left", padx=(0, 5))

                title_text = self.truncate_title(show.title)
                show_cb = ctk.CTkCheckBox(show_inner, text=title_text,
                                         variable=show_var,
                                         command=lambda s=show, v=show_var, f=show_frame: self.on_show_selected(s, v, f))
                show_cb.pack(side="left", fill="x", expand=True)

                show_frame.expand_btn = expand_btn
                show_frame.expand_var = expand_var
                show_frame.show_var = show_var
                show_frame.show_obj = show
                show_frame.show_cb = show_cb
                show_frame.season_frames = []
                self.top_level_frames.append(show_frame)

            # Update external pagination controls
            for widget in self.pagination_frame.winfo_children():
                widget.destroy()

            prev_btn = ctk.CTkButton(self.pagination_frame, text="◀ Previous",
                                     width=100, height=32,
                                     command=lambda: load_show_page(page_num - 1),
                                     state="normal" if page_num > 1 else "disabled")
            prev_btn.grid(row=0, column=0, padx=5)

            page_label = ctk.CTkLabel(self.pagination_frame,
                                     text=f"Page {page_num} of {total_pages}",
                                     font=ctk.CTkFont(size=12))
            page_label.grid(row=0, column=1, padx=5)

            next_btn = ctk.CTkButton(self.pagination_frame, text="Next ▶",
                                     width=100, height=32,
                                     command=lambda: load_show_page(page_num + 1),
                                     state="normal" if page_num < total_pages else "disabled")
            next_btn.grid(row=0, column=2, padx=5)

            # Show pagination frame
            self.pagination_frame.grid()

            # Update status
            self.update_status(f"Page {page_num}/{total_pages} ({start_idx + 1}-{end_idx} of {total_shows} shows)")

        # Store the load function so it can be called when filters change
        self.load_show_page = load_show_page

        # Load first page
        if shows:
            load_show_page(1)
        else:
            self.pagination_frame.grid_remove()
            self.update_status("No shows found")

    def toggle_show(self, show, frame, expand_var):
        """Toggle show expansion to show seasons/episodes."""
        if expand_var.get():
            # Collapse
            expand_var.set(False)
            frame.expand_btn.configure(text="▶")
            # Remove season frames
            for widget in frame.winfo_children():
                if widget != frame.expand_btn.master:
                    widget.destroy()
        else:
            # Expand
            expand_var.set(True)
            frame.expand_btn.configure(text="▼")

            # Show loading indicator
            loading_container = ctk.CTkFrame(frame, fg_color="transparent")
            loading_container.pack(fill="x", padx=(35, 0), pady=(5, 0))
            loading_label = ctk.CTkLabel(loading_container, text="Loading seasons...",
                                        font=ctk.CTkFont(size=11), text_color="gray")
            loading_label.pack(anchor="w")

            # Load seasons in thread
            def load_seasons():
                if self._is_destroyed:
                    return
                try:
                    seasons = show.seasons()
                    # Remove loading indicator before populating
                    self.safe_after(0, lambda: loading_container.destroy())
                    self.safe_after(0, lambda: self.populate_seasons(frame, seasons))
                except Exception as e:
                    self.safe_after(0, lambda: loading_container.destroy())
                    self.safe_after(0, lambda: self.log(f"Error loading seasons: {e}"))

            threading.Thread(target=load_seasons, daemon=True).start()

    def populate_seasons(self, show_frame, seasons):
        """Populate seasons under a show."""
        season_container = ctk.CTkFrame(show_frame, fg_color="transparent")
        season_container.pack(fill="x", padx=(35, 0), pady=(5, 0))

        # Clear season frames list
        show_frame.season_frames = []

        for season in seasons:
            season_frame = ctk.CTkFrame(season_container, fg_color="transparent")
            season_frame.pack(fill="x", pady=2)

            # Season inner frame (for button and checkbox)
            season_inner = ctk.CTkFrame(season_frame, fg_color="transparent")
            season_inner.pack(fill="x")

            season_var = ctk.BooleanVar()
            expand_var = ctk.BooleanVar(value=False)

            expand_btn = ctk.CTkButton(season_inner, text="▶", width=25, height=20,
                                       fg_color="transparent", font=ctk.CTkFont(size=10),
                                       command=lambda s=season, f=season_frame, v=expand_var: self.toggle_season(s, f, v))
            expand_btn.pack(side="left", padx=(0, 5))

            season_cb = ctk.CTkCheckBox(season_inner, text=f"Season {season.seasonNumber}",
                                       variable=season_var,
                                       command=lambda s=season, v=season_var, f=season_frame: self.on_season_selected(s, v, f))
            season_cb.pack(side="left")

            season_frame.expand_btn = expand_btn
            season_frame.expand_var = expand_var
            season_frame.season_var = season_var
            season_frame.season_obj = season
            season_frame.season_inner = season_inner
            season_frame.season_cb = season_cb  # Store checkbox reference
            season_frame.episode_checkboxes = []  # Initialize list for episode checkboxes
            season_frame.episode_vars = []  # Initialize list for episode variables

            # Add this season frame to the parent show's list
            show_frame.season_frames.append(season_frame)

    def toggle_season(self, season, frame, expand_var):
        """Toggle season expansion to show episodes."""
        if expand_var.get():
            # Collapse
            expand_var.set(False)
            frame.expand_btn.configure(text="▶")
            # Remove episode containers (keep season_inner)
            for widget in frame.winfo_children():
                if widget != frame.season_inner:
                    widget.destroy()
        else:
            # Expand
            expand_var.set(True)
            frame.expand_btn.configure(text="▼")

            # Show loading indicator
            loading_container = ctk.CTkFrame(frame, fg_color="transparent")
            loading_container.pack(fill="x", padx=(25, 0), pady=(2, 0))
            loading_label = ctk.CTkLabel(loading_container, text="Loading episodes...",
                                        font=ctk.CTkFont(size=10), text_color="gray")
            loading_label.pack(anchor="w")

            # Load episodes in thread
            def load_episodes():
                if self._is_destroyed:
                    return
                try:
                    episodes = season.episodes()
                    # Remove loading indicator before populating
                    self.safe_after(0, lambda: loading_container.destroy())
                    self.safe_after(0, lambda: self.populate_episodes(frame, episodes))
                except Exception as e:
                    self.safe_after(0, lambda: loading_container.destroy())
                    self.safe_after(0, lambda: self.log(f"Error loading episodes: {e}"))

            threading.Thread(target=load_episodes, daemon=True).start()

    def populate_episodes(self, season_frame, episodes):
        """Populate episodes under a season with page navigation."""
        # Container will be recreated on each page load
        season_frame.all_episodes = episodes
        season_frame.current_episode_page = 1
        season_frame.episode_checkboxes = []
        season_frame.episode_vars = []

        # Pagination settings
        EPISODES_PER_PAGE = 15
        total_episodes = len(episodes)
        total_pages = (total_episodes + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE

        def load_episode_page(page_num):
            """Load a specific page of episodes."""
            if self._is_destroyed or page_num < 1 or page_num > total_pages:
                return

            # Clear existing episode container if it exists
            if hasattr(season_frame, 'episode_container'):
                try:
                    season_frame.episode_container.destroy()
                except:
                    pass

            # Create new container
            episode_container = ctk.CTkFrame(season_frame, fg_color="transparent")
            episode_container.pack(fill="x", padx=(25, 0), pady=(2, 0))
            season_frame.episode_container = episode_container
            season_frame.current_episode_page = page_num

            # Calculate range
            start_idx = (page_num - 1) * EPISODES_PER_PAGE
            end_idx = min(start_idx + EPISODES_PER_PAGE, total_episodes)

            # Create episode widgets for this page
            page_frames = []
            for i in range(start_idx, end_idx):
                episode = episodes[i]
                episode_var = ctk.BooleanVar()

                ep_frame = ctk.CTkFrame(episode_container, fg_color="transparent")
                ep_frame.pack(fill="x", pady=1)

                status_label = ctk.CTkLabel(ep_frame, text="○", width=20,
                                           text_color="gray", font=ctk.CTkFont(size=12, weight="bold"))
                status_label.pack(side="left", padx=(5, 5))

                ep_title_text = self.truncate_title(f"E{episode.index:02d} - {episode.title}", max_length=70)
                ep_cb = ctk.CTkCheckBox(ep_frame,
                                       text=ep_title_text,
                                       variable=episode_var,
                                       command=lambda e=episode, v=episode_var: self.on_item_selected(e, v))
                ep_cb.pack(side="left", anchor="w", fill="x", expand=True)

                ep_frame.status_label = status_label
                ep_frame.item_obj = episode
                page_frames.append(ep_frame)

            # Add pagination controls if more than one page
            if total_pages > 1:
                pagination_frame = ctk.CTkFrame(episode_container, fg_color="transparent")
                pagination_frame.pack(fill="x", pady=(5, 0), padx=5)

                prev_btn = ctk.CTkButton(pagination_frame, text="◀",
                                         width=60, height=24,
                                         command=lambda: load_episode_page(page_num - 1),
                                         state="normal" if page_num > 1 else "disabled",
                                         fg_color="transparent", border_width=1,
                                         text_color=("gray10", "gray90"))
                prev_btn.pack(side="left", padx=2)

                page_label = ctk.CTkLabel(pagination_frame,
                                         text=f"{page_num}/{total_pages}",
                                         font=ctk.CTkFont(size=10))
                page_label.pack(side="left", expand=True)

                next_btn = ctk.CTkButton(pagination_frame, text="▶",
                                         width=60, height=24,
                                         command=lambda: load_episode_page(page_num + 1),
                                         state="normal" if page_num < total_pages else "disabled",
                                         fg_color="transparent", border_width=1,
                                         text_color=("gray10", "gray90"))
                next_btn.pack(side="right", padx=2)

            # Load subtitle status in background
            def start_subtitle_status_loading():
                def load_subtitle_status():
                    if self._is_destroyed:
                        return
                    for frame in page_frames:
                        if self._is_destroyed:
                            return
                        try:
                            item = frame.item_obj
                            has_subs = self.check_has_subtitles(item)
                            status_icon = "✓" if has_subs else "✗"
                            status_color = ("green", "#2d7a2d") if has_subs else ("red", "#8b0000")

                            def update_status_label(frame_ref=frame, icon=status_icon, color=status_color):
                                try:
                                    # Check if widget still exists before updating
                                    if frame_ref.winfo_exists() and hasattr(frame_ref, 'status_label'):
                                        frame_ref.status_label.configure(text=icon, text_color=color)
                                except:
                                    pass

                            self.safe_after(0, update_status_label)
                        except:
                            pass
                threading.Thread(target=load_subtitle_status, daemon=True).start()

            self.after(50, start_subtitle_status_loading)

        # Load first page
        if episodes:
            load_episode_page(1)

    def on_item_selected(self, item, var):
        """Handle individual item (movie/episode) selection."""
        if var.get():
            if item not in self.selected_items:
                self.selected_items.append(item)
            # Show current subtitle status when selected
            self.show_subtitle_status(item)
        else:
            if item in self.selected_items:
                self.selected_items.remove(item)
        self.update_selection_label()

    def on_show_selected(self, show, var, show_frame):
        """Handle show selection (selects all episodes)."""
        def load_and_select():
            if self._is_destroyed:
                return
            try:
                episodes = show.episodes()
                if var.get():
                    # Show summary for the show
                    self.safe_after(0, lambda: self.log(f"\n📺 {show.title} - Selected all {len(episodes)} episodes"))
                    self.safe_after(0, lambda: self.log(f"  Tip: Uncheck the show to select individual seasons/episodes"))

                    for ep in episodes:
                        if ep not in self.selected_items:
                            self.selected_items.append(ep)

                    # Check and disable all season and episode checkboxes when show is selected
                    if hasattr(show_frame, 'season_frames'):
                        for season_frame in show_frame.season_frames:
                            # Check and disable season checkbox
                            if hasattr(season_frame, 'season_cb') and hasattr(season_frame, 'season_var'):
                                try:
                                    self.safe_after(0, lambda v=season_frame.season_var: v.set(True))
                                    self.safe_after(0, lambda cb=season_frame.season_cb: cb.configure(state="disabled"))
                                except:
                                    pass

                            # Check and disable episode checkboxes
                            if hasattr(season_frame, 'episode_checkboxes') and hasattr(season_frame, 'episode_vars'):
                                for ep_cb, ep_var in zip(season_frame.episode_checkboxes, season_frame.episode_vars):
                                    try:
                                        self.safe_after(0, lambda v=ep_var: v.set(True))
                                        self.safe_after(0, lambda cb=ep_cb: cb.configure(state="disabled"))
                                    except:
                                        pass
                else:
                    for ep in episodes:
                        if ep in self.selected_items:
                            self.selected_items.remove(ep)

                    # Uncheck and enable all season and episode checkboxes when show is deselected
                    if hasattr(show_frame, 'season_frames'):
                        for season_frame in show_frame.season_frames:
                            # Uncheck and enable season checkbox
                            if hasattr(season_frame, 'season_cb') and hasattr(season_frame, 'season_var'):
                                try:
                                    self.safe_after(0, lambda cb=season_frame.season_cb: cb.configure(state="normal"))
                                    self.safe_after(0, lambda v=season_frame.season_var: v.set(False))
                                except:
                                    pass

                            # Uncheck and enable episode checkboxes
                            if hasattr(season_frame, 'episode_checkboxes') and hasattr(season_frame, 'episode_vars'):
                                for ep_cb, ep_var in zip(season_frame.episode_checkboxes, season_frame.episode_vars):
                                    try:
                                        self.safe_after(0, lambda cb=ep_cb: cb.configure(state="normal"))
                                        self.safe_after(0, lambda v=ep_var: v.set(False))
                                    except:
                                        pass

                self.safe_after(0, self.update_selection_label)
            except Exception as e:
                self.safe_after(0, lambda: self.log(f"Error: {e}"))

        threading.Thread(target=load_and_select, daemon=True).start()

    def on_season_selected(self, season, var, season_frame):
        """Handle season selection (selects all episodes in season)."""
        def load_and_select():
            if self._is_destroyed:
                return
            try:
                episodes = season.episodes()
                if var.get():
                    # Show status header for the season
                    season_title = f"{season.parentTitle} - Season {season.seasonNumber}"
                    self.safe_after(0, lambda: self.log(f"\n📺 {season_title} ({len(episodes)} episodes)"))

                    for ep in episodes:
                        if ep not in self.selected_items:
                            self.selected_items.append(ep)

                    # Check all episode checkboxes and disable them when season is selected
                    if hasattr(season_frame, 'episode_checkboxes') and hasattr(season_frame, 'episode_vars'):
                        for i, (ep_cb, ep_var) in enumerate(zip(season_frame.episode_checkboxes, season_frame.episode_vars)):
                            try:
                                # Set checkbox to checked
                                self.safe_after(0, lambda v=ep_var: v.set(True))
                                # Then disable it
                                self.safe_after(0, lambda cb=ep_cb: cb.configure(state="disabled"))
                            except:
                                pass

                    # Show subtitle status for all episodes in the season
                    for ep in episodes:
                        self.show_subtitle_status(ep)
                else:
                    for ep in episodes:
                        if ep in self.selected_items:
                            self.selected_items.remove(ep)

                    # Uncheck all episode checkboxes and enable them when season is deselected
                    if hasattr(season_frame, 'episode_checkboxes') and hasattr(season_frame, 'episode_vars'):
                        for i, (ep_cb, ep_var) in enumerate(zip(season_frame.episode_checkboxes, season_frame.episode_vars)):
                            try:
                                # Enable checkbox first
                                self.safe_after(0, lambda cb=ep_cb: cb.configure(state="normal"))
                                # Then uncheck it
                                self.safe_after(0, lambda v=ep_var: v.set(False))
                            except:
                                pass

                self.safe_after(0, self.update_selection_label)
            except Exception as e:
                self.safe_after(0, lambda: self.log(f"Error: {e}"))

        threading.Thread(target=load_and_select, daemon=True).start()

    def select_all_items(self):
        """Select all items in current library."""
        if not self.current_library:
            return

        def load_and_select():
            if self._is_destroyed:
                return
            try:
                self.selected_items.clear()
                if self.current_library.type == 'movie':
                    movies = self.current_library.all()
                    self.selected_items.extend(movies)
                elif self.current_library.type == 'show':
                    shows = self.current_library.all()
                    for show in shows:
                        episodes = show.episodes()
                        self.selected_items.extend(episodes)
                self.safe_after(0, self.update_selection_label)
                self.safe_after(0, lambda: self.log("✓ Selected all items\n"))
            except Exception as e:
                self.safe_after(0, lambda: self.log(f"Error: {e}"))

        threading.Thread(target=load_and_select, daemon=True).start()

    def clear_selection(self):
        """Clear all selections."""
        self.selected_items.clear()
        self.update_selection_label()

    def update_selection_label(self):
        """Update selection count label."""
        count = len(self.selected_items)
        self.selection_label.configure(text=f"{count} item{'s' if count != 1 else ''} selected")

        # Enable/disable action buttons based on selection
        state = "normal" if count > 0 else "disabled"
        self.search_btn.configure(state=state)
        self.list_btn.configure(state=state)

        # Download button only enabled if we have search results
        download_state = "normal" if self.search_results else "disabled"
        self.download_btn.configure(state=download_state)

    def show_subtitle_status(self, item):
        """Show current subtitle status for a video item."""
        def check_status():
            if self._is_destroyed:
                return
            try:
                title = self._get_item_title(item)

                # Reload item to get fresh data from Plex server
                try:
                    item.reload()
                except:
                    pass  # If reload fails, continue with existing data

                has_subs = False
                selected_sub = None
                all_subs_info = []

                for media in item.media:
                    for part in media.parts:
                        subs = part.subtitleStreams()
                        if subs:
                            has_subs = True
                            for sub in subs:
                                # Get subtitle info
                                lang = sub.language if hasattr(sub, 'language') and sub.language else "Unknown"
                                codec = sub.codec if hasattr(sub, 'codec') and sub.codec else "?"
                                forced = "[F]" if hasattr(sub, 'forced') and sub.forced else ""
                                sdh = "[SDH]" if hasattr(sub, 'hearingImpaired') and sub.hearingImpaired else ""

                                # Get subtitle file name or title
                                sub_detail = ""
                                if hasattr(sub, 'title') and sub.title:
                                    sub_detail = f" - {sub.title}"
                                elif hasattr(sub, 'key') and sub.key:
                                    try:
                                        filename = sub.key.split('/')[-1]
                                        if filename:
                                            sub_detail = f" - {filename}"
                                    except:
                                        pass

                                # Check if this subtitle is selected
                                is_selected = False
                                if hasattr(sub, 'selected'):
                                    is_selected = bool(sub.selected)

                                status = "[SEL]" if is_selected else "     "

                                # Store info for all subtitles
                                sub_info = f"{status} {lang} ({codec}) {forced} {sdh}{sub_detail}".strip()
                                all_subs_info.append(sub_info)

                                if is_selected and not selected_sub:
                                    selected_sub = f"{lang} ({codec}) {forced} {sdh}{sub_detail}".strip()

                # Format output message
                msg = f"📊 {title}"
                if selected_sub:
                    msg += f"\n  ✓ Current: {selected_sub}"
                elif has_subs:
                    msg += f"\n  ✗ Current: None (no subtitle selected)"
                else:
                    msg += f"\n  ✗ Current: None (no subtitles available)"

                # Show all available subtitles
                if all_subs_info:
                    msg += "\n  Available subtitles:"
                    for sub_info in all_subs_info:
                        msg += f"\n    {sub_info}"

                self.safe_after(0, lambda m=msg: self.log(m))

            except Exception as e:
                title = self._get_item_title(item)
                self.safe_after(0, lambda err=str(e): self.log(f"📊 {title}\n  Error: {err}"))

        # Run in thread to avoid blocking UI
        threading.Thread(target=check_status, daemon=True).start()

    def check_has_subtitles(self, item, force_refresh=False):
        """Check if an item has subtitles (fast check, uses cache)."""
        item_id = item.ratingKey

        # Return cached result if available (unless forced refresh)
        if not force_refresh and item_id in self.subtitle_status_cache:
            return self.subtitle_status_cache[item_id]

        # Reload item to get fresh subtitle data from server
        try:
            item.reload()
        except:
            pass  # If reload fails, continue with existing data

        # Check subtitle status
        try:
            for media in item.media:
                for part in media.parts:
                    subs = part.subtitleStreams()
                    if subs:
                        self.subtitle_status_cache[item_id] = True
                        return True
        except:
            pass

        self.subtitle_status_cache[item_id] = False
        return False

    def refresh_subtitle_indicators(self, items_to_refresh=None):
        """Refresh subtitle status indicators in the browser."""
        def update_indicator(frame):
            if not hasattr(frame, 'status_label') or not hasattr(frame, 'item_obj'):
                return

            try:
                # Check if widget still exists before accessing
                if not frame.winfo_exists():
                    return

                item = frame.item_obj
                has_subs = self.check_has_subtitles(item, force_refresh=True)

                # Update indicator
                status_icon = "✓" if has_subs else "✗"
                status_color = ("green", "#2d7a2d") if has_subs else ("red", "#8b0000")
                frame.status_label.configure(text=status_icon, text_color=status_color)
            except:
                pass

        def search_frames_recursive(widget, item_ids=None):
            """Recursively search for frames with item_obj."""
            # Check current widget
            if hasattr(widget, 'item_obj'):
                if item_ids is None or widget.item_obj.ratingKey in item_ids:
                    update_indicator(widget)

            # Recursively check all children
            try:
                for child in widget.winfo_children():
                    search_frames_recursive(child, item_ids)
            except:
                pass

        # If specific items provided, only refresh those
        if items_to_refresh:
            item_ids = {item.ratingKey for item in items_to_refresh}
            # Search all widgets recursively
            for widget in self.browser_scroll.winfo_children():
                search_frames_recursive(widget, item_ids)
        else:
            # Refresh all indicators
            for widget in self.browser_scroll.winfo_children():
                search_frames_recursive(widget)

    def get_video_items(self):
        """Get selected video items."""
        return self.selected_items

    def populate_subtitle_selection_panel(self):
        """Populate the info panel with search results for subtitle selection."""
        # Clear existing widgets
        self.clear_info_panel()

        if not self.search_results:
            return

        # Configure panel for subtitle selection
        self.info_panel_title.configure(text="📝 Select Subtitles to Download")
        self.info_panel_action_btn.configure(text="Clear", command=self.clear_info_panel)

        # Show the info panel
        self.info_frame.grid()

        row = 0
        for item, subs_list in self.search_results.items():
            if not subs_list:
                continue

            title = self._get_item_title(item)

            # Get actual file name from Plex
            actual_filename = "Unknown"
            try:
                for media in item.media:
                    for part in media.parts:
                        if part.file:
                            actual_filename = os.path.basename(part.file)
                            break
                    if actual_filename != "Unknown":
                        break
            except:
                pass

            # Video header frame
            video_frame = ctk.CTkFrame(self.info_scroll, fg_color=("gray85", "gray25"))
            video_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            video_frame.grid_columnconfigure(0, weight=1)

            # Video title
            ctk.CTkLabel(video_frame, text=title, font=ctk.CTkFont(weight="bold"),
                        anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))

            # File name
            ctk.CTkLabel(video_frame, text=f"File: {actual_filename}",
                        font=ctk.CTkFont(size=11), text_color="gray",
                        anchor="w").grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

            # Subtitle options
            selection_var = ctk.IntVar(value=0)  # Default to first subtitle
            self.subtitle_selections[item] = selection_var

            for i, sub in enumerate(subs_list[:10], 0):  # Show top 10 options
                # Get subtitle info
                release_info = (
                    getattr(sub, 'movie_release_name', None) or
                    getattr(sub, 'release', None) or
                    getattr(sub, 'filename', None) or
                    getattr(sub, 'info', None) or
                    f"ID: {getattr(sub, 'subtitle_id', 'Unknown')}"
                )
                provider_info = getattr(sub, 'provider_name', 'unknown')

                # Radio button for this subtitle
                radio_text = f"[{provider_info}] {str(release_info)[:100]}"
                radio = ctk.CTkRadioButton(video_frame, text=radio_text, variable=selection_var,
                                          value=i)
                radio.grid(row=i+2, column=0, sticky="w", padx=20, pady=2)

            if len(subs_list) > 10:
                ctk.CTkLabel(video_frame, text=f"... and {len(subs_list) - 10} more (showing top 10)",
                            font=ctk.CTkFont(size=11), text_color="gray").grid(
                    row=12, column=0, sticky="w", padx=20, pady=(2, 10))
            else:
                # Add padding at the end
                ctk.CTkLabel(video_frame, text="").grid(row=len(subs_list)+2, column=0, pady=5)

            row += 1

    def search_subtitles(self):
        """Search for available subtitles (does not download)."""
        items = self.get_video_items()
        if not items:
            self.update_status("No items selected")
            return

        # Show confirmation dialog for bulk operations
        if len(items) >= 5:
            if not self.show_confirmation_dialog(
                "Search Confirmation",
                f"About to search for subtitles for {len(items)} item(s).\n\nContinue?"
            ):
                self.update_status("Search cancelled")
                return

        def task():
            self.show_progress()
            self.disable_action_buttons()

            language_name = self.search_lang_combo.get()
            language_code = SEARCH_LANGUAGES[language_name]
            provider_name = self.provider_combo.get()
            provider = SUBTITLE_PROVIDERS[provider_name]
            sdh = self.sdh_var.get()

            self.safe_after(0, lambda: self.update_status(f"Searching {len(items)} item(s) on {provider_name}..."))

            # Clear previous search results and info panel
            self.search_results = {}
            self.safe_after(0, self.clear_info_panel)

            from subliminal import list_subtitles
            # Use fromalpha2 for 2-letter codes (en, es, etc.)
            language_obj = Language.fromalpha2(language_code)

            total_found = 0
            for item in items:
                title = self._get_item_title(item)
                try:
                    # Get actual file name from Plex
                    actual_filename = "Unknown"
                    try:
                        for media in item.media:
                            for part in media.parts:
                                if part.file:
                                    actual_filename = os.path.basename(part.file)
                                    break
                            if actual_filename != "Unknown":
                                break
                    except:
                        pass

                    # Update status for current item
                    self.safe_after(0, lambda t=title: self.update_status(f"Searching: {t}"))

                    # Create subliminal Video object from Plex metadata (no file access needed)
                    if isinstance(item, Episode):
                        # TV Episode - create a fake filename for subliminal
                        fake_name = f"{item.grandparentTitle}.S{item.seasonNumber:02d}E{item.index:02d}.mkv"
                        video = SubliminalEpisode(
                            name=fake_name,
                            series=item.grandparentTitle,
                            season=item.seasonNumber,
                            episodes=item.index  # Single episode number as int
                        )
                        # Set additional attributes
                        video.title = item.title
                        if hasattr(item, 'year') and item.year:
                            video.year = item.year
                    elif isinstance(item, Movie):
                        # Movie - create a fake filename
                        year = getattr(item, 'year', '')
                        fake_name = f"{item.title}.{year}.mkv" if year else f"{item.title}.mkv"
                        video = SubliminalMovie(
                            name=fake_name,
                            title=item.title,
                            year=getattr(item, 'year', None)
                        )
                    else:
                        self.log(f"  ✗ Unsupported item type")
                        continue

                    # List available subtitles
                    subtitles = list_subtitles({video}, {language_obj}, providers=[provider])

                    if video in subtitles and subtitles[video]:
                        subs_list = list(subtitles[video])
                        self.search_results[item] = subs_list
                        total_found += len(subs_list)

                except Exception as e:
                    self.log(f"Error searching {title}: {e}")

            # Update status and show results
            if self.search_results:
                self.safe_after(0, lambda: self.update_status(
                    f"Found {total_found} subtitle(s) for {len(self.search_results)} item(s) - Select and download"))
                # Populate the selection panel
                self.safe_after(0, self.populate_subtitle_selection_panel)
            else:
                self.safe_after(0, lambda: self.update_status("No subtitles found"))

            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

    def download_subtitles(self):
        """Download selected subtitles from search results."""
        if not self.search_results:
            self.update_status("No search results - Search first")
            return

        # Show confirmation dialog for bulk operations
        num_items = len(self.search_results)
        if num_items >= 5:
            if not self.show_confirmation_dialog(
                "Download Confirmation",
                f"About to download {num_items} subtitle(s).\n\nContinue?"
            ):
                self.update_status("Download cancelled")
                return

        def task():
            self.show_progress()
            self.disable_action_buttons()

            language_name = self.search_lang_combo.get()
            language_code = SEARCH_LANGUAGES[language_name]
            # Use fromalpha2 for 2-letter codes (en, es, etc.)
            language_obj = Language.fromalpha2(language_code)

            provider_name = self.provider_combo.get()
            provider = SUBTITLE_PROVIDERS[provider_name]

            self.safe_after(0, lambda: self.update_status(f"Downloading {len(self.search_results)} subtitle(s)..."))

            success_count = 0
            successful_items = []  # Track items that successfully got subtitles
            for item, subs_list in self.search_results.items():
                title = self._get_item_title(item)
                try:
                    if not subs_list:
                        continue

                    # Get selected subtitle from selection panel
                    if item in self.subtitle_selections:
                        selected_index = self.subtitle_selections[item].get()
                        if selected_index >= len(subs_list):
                            selected_index = 0  # Fallback to first if out of range
                        selected_sub = subs_list[selected_index]
                    else:
                        # Fallback to first subtitle if no selection exists
                        selected_sub = subs_list[0]

                    # Update status
                    self.safe_after(0, lambda t=title: self.update_status(f"Downloading: {t}"))

                    # Download the subtitle content using subliminal API
                    download_subtitles([selected_sub], providers=[provider])

                    # Save to temporary file
                    import tempfile
                    temp_dir = tempfile.gettempdir()

                    # Create filename based on item type
                    if isinstance(item, Episode):
                        subtitle_filename = f"{item.grandparentTitle}.S{item.seasonNumber:02d}E{item.index:02d}.{language_code}.srt"
                    else:
                        subtitle_filename = f"{item.title}.{language_code}.srt"

                    # Remove invalid filename characters
                    subtitle_filename = "".join(c for c in subtitle_filename if c.isalnum() or c in (' ', '.', '_', '-'))
                    subtitle_path = os.path.join(temp_dir, subtitle_filename)

                    # Write subtitle content to file
                    with open(subtitle_path, 'wb') as f:
                        f.write(selected_sub.content)

                    # Save subtitle based on user preference
                    if self.subtitle_save_method == 'file':
                        # Save subtitle next to video file
                        try:
                            # Get video file path from Plex
                            if hasattr(item, 'media') and item.media:
                                video_path = item.media[0].parts[0].file
                                video_dir = os.path.dirname(video_path)
                                video_base = os.path.splitext(os.path.basename(video_path))[0]

                                # Create subtitle filename: VideoName.{lang}.srt
                                final_subtitle_filename = f"{video_base}.{language_code}.srt"
                                final_subtitle_path = os.path.join(video_dir, final_subtitle_filename)

                                # Copy subtitle file to video directory
                                import shutil
                                shutil.copy2(subtitle_path, final_subtitle_path)

                                self.log(f"Saved subtitle to: {final_subtitle_path}")

                                # Trigger Plex partial scan to detect new subtitle
                                try:
                                    # Get the library section for this item
                                    if isinstance(item, Episode):
                                        library_section = item.section()
                                    else:
                                        library_section = item.section()

                                    # Scan the specific file path
                                    library_section.update(video_dir)
                                    self.log(f"Triggered Plex scan for: {video_dir}")
                                except Exception as scan_error:
                                    self.log(f"Note: Could not trigger Plex scan: {scan_error}")
                                    self.log("You may need to manually refresh the library in Plex")
                            else:
                                self.log(f"Warning: Could not get video file path for {title}")
                                # Fallback to Plex upload
                                item.uploadSubtitles(subtitle_path)
                        except Exception as file_error:
                            self.log(f"Error saving subtitle file: {file_error}")
                            self.log("Falling back to Plex upload method")
                            # Fallback to Plex upload if file save fails
                            item.uploadSubtitles(subtitle_path)
                    else:
                        # Upload to Plex server (default behavior)
                        item.uploadSubtitles(subtitle_path)

                    # Clean up temp file
                    try:
                        os.remove(subtitle_path)
                    except:
                        pass

                    success_count += 1
                    successful_items.append(item)

                except Exception as e:
                    self.log(f"Download error for {title}: {e}", level="error")

            # Refresh subtitle indicators for successful items
            if successful_items:
                self.safe_after(0, lambda: self.update_status(f"Downloaded {success_count}/{len(self.search_results)} - Refreshing indicators..."))
                # Reload items to get fresh subtitle data
                for item in successful_items:
                    try:
                        item.reload()
                    except:
                        pass
                self.safe_after(0, lambda: self.refresh_subtitle_indicators(successful_items))
                self.safe_after(0, lambda: self.update_status(f"✓ Downloaded {success_count}/{len(self.search_results)} subtitle(s)"))
            else:
                self.safe_after(0, lambda: self.update_status("Download failed - Check log for errors"))

            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

    def dry_run_missing_subtitles(self):
        """Preview which subtitles would be available for items missing them (no download)."""
        items = self.get_video_items()
        if not items:
            self.update_status("No items selected")
            return

        def task():
            self.show_progress()
            self.disable_action_buttons()

            language_name = self.search_lang_combo.get()
            language_code = SEARCH_LANGUAGES[language_name]
            language_obj = Language.fromalpha2(language_code)
            provider_name = self.provider_combo.get()
            provider = SUBTITLE_PROVIDERS[provider_name]

            self.safe_after(0, lambda: self.update_status(f"Dry run: Checking {len(items)} item(s) for missing subtitles..."))
            self.log(f"Starting dry run for {len(items)} selected items...")

            try:
                # Filter items missing subtitles
                items_missing_subs = []
                for i, item in enumerate(items):
                    if self._is_destroyed:
                        return

                    if (i + 1) % 10 == 0:
                        self.safe_after(0, lambda count=i+1, total=len(items):
                            self.update_status(f"Checking items... ({count}/{total})"))

                    if not self.check_has_subtitles(item, force_refresh=False):
                        items_missing_subs.append(item)

                if not items_missing_subs:
                    self.log(f"✓ All selected items already have subtitles!")
                    self.safe_after(0, lambda: self.update_status("All selected items already have subtitles"))
                    self.safe_after(0, lambda: messagebox.showinfo(
                        "Dry Run Complete", "All selected items already have subtitles.", parent=self))
                    self.hide_progress()
                    self.enable_action_buttons()
                    return

                self.log(f"Found {len(items_missing_subs)} items missing subtitles out of {len(items)} selected")
                self.safe_after(0, lambda: self.update_status(f"Searching for available subtitles..."))

                # Search for available subtitles
                from subliminal import list_subtitles
                preview_results = {}  # {item: [subtitles]}
                total_subs_found = 0

                for i, item in enumerate(items_missing_subs):
                    if self._is_destroyed:
                        return

                    title = self._get_item_title(item)
                    self.safe_after(0, lambda t=title, idx=i+1, total=len(items_missing_subs):
                        self.update_status(f"Searching ({idx}/{total}): {t}"))

                    try:
                        # Create subliminal Video object
                        if isinstance(item, Episode):
                            fake_name = f"{item.grandparentTitle}.S{item.seasonNumber:02d}E{item.index:02d}.mkv"
                            video = SubliminalEpisode(
                                name=fake_name,
                                series=item.grandparentTitle,
                                season=item.seasonNumber,
                                episodes=item.index
                            )
                            video.title = item.title
                            if hasattr(item, 'year') and item.year:
                                video.year = item.year
                        elif isinstance(item, Movie):
                            year = getattr(item, 'year', '')
                            fake_name = f"{item.title}.{year}.mkv" if year else f"{item.title}.mkv"
                            video = SubliminalMovie(
                                name=fake_name,
                                title=item.title,
                                year=getattr(item, 'year', None)
                            )
                        else:
                            continue

                        # Search for subtitles
                        subtitles = list_subtitles({video}, {language_obj}, providers=[provider])

                        if video in subtitles and subtitles[video]:
                            subs_list = list(subtitles[video])
                            preview_results[item] = subs_list
                            total_subs_found += len(subs_list)
                            self.log(f"  ✓ {title} - {len(subs_list)} subtitle(s) available")
                        else:
                            preview_results[item] = []
                            self.log(f"  ✗ {title} - No subtitles found")

                    except Exception as e:
                        preview_results[item] = []
                        self.log(f"  ✗ {title} - Error: {e}")

                # Display results in info panel
                self.safe_after(0, lambda: self.display_dry_run_results(preview_results, language_name, provider_name))

                items_with_subs = sum(1 for subs in preview_results.values() if subs)
                self.log(f"\nDry run complete: {items_with_subs}/{len(items_missing_subs)} items have available subtitles ({total_subs_found} total)")
                self.safe_after(0, lambda: self.update_status(
                    f"✓ Dry run complete: {items_with_subs}/{len(items_missing_subs)} items have subtitles available"))

            except Exception as e:
                self.log(f"✗ Dry run error: {e}", level="error")
                self.safe_after(0, lambda: self.update_status(f"Error: {e}"))

            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

    def display_dry_run_results(self, results, language_name, provider_name):
        """Display dry run results in info panel."""
        self.clear_info_panel()
        self.info_panel_title.configure(text=f"👁 Dry Run Preview - {language_name} ({provider_name})")
        self.info_panel_action_btn.configure(text="Close", command=self.clear_info_panel)
        self.info_frame.grid()

        if not results:
            ctk.CTkLabel(self.info_scroll, text="No results to display",
                        font=ctk.CTkFont(size=12), text_color="gray").grid(row=0, column=0, pady=20)
            return

        row = 0
        items_with_subs = 0
        items_without_subs = 0

        for item, subs_list in results.items():
            title = self._get_item_title(item)

            # Create frame for this item
            item_frame = ctk.CTkFrame(self.info_scroll, fg_color=("gray85", "gray25"))
            item_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            item_frame.grid_columnconfigure(0, weight=1)

            if subs_list:
                items_with_subs += 1
                # Title with checkmark
                title_label = ctk.CTkLabel(item_frame, text=f"✓ {title}",
                                          font=ctk.CTkFont(weight="bold"), text_color=("green", "#2d7a2d"),
                                          anchor="w")
                title_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

                # Number of subtitles available
                count_label = ctk.CTkLabel(item_frame, text=f"{len(subs_list)} subtitle(s) would be available",
                                          font=ctk.CTkFont(size=11), text_color="gray",
                                          anchor="w")
                count_label.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
            else:
                items_without_subs += 1
                # Title with X
                title_label = ctk.CTkLabel(item_frame, text=f"✗ {title}",
                                          font=ctk.CTkFont(weight="bold"), text_color=("red", "#8b0000"),
                                          anchor="w")
                title_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

                # No subtitles message
                no_subs_label = ctk.CTkLabel(item_frame, text="No subtitles found",
                                            font=ctk.CTkFont(size=11), text_color="gray",
                                            anchor="w")
                no_subs_label.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))

            row += 1

        # Summary at the top
        summary_frame = ctk.CTkFrame(self.info_scroll, fg_color=("gray75", "gray30"))
        summary_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        summary_frame.grid_columnconfigure(0, weight=1)

        summary_text = f"📊 Summary: {items_with_subs} items have subtitles | {items_without_subs} items without"
        summary_label = ctk.CTkLabel(summary_frame, text=summary_text,
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     anchor="w")
        summary_label.grid(row=0, column=0, sticky="ew", padx=15, pady=10)

        # Shift all item frames down
        for widget in self.info_scroll.winfo_children():
            if widget != summary_frame:
                current_row = widget.grid_info()['row']
                widget.grid(row=current_row + 1)

    def list_subtitles(self):
        """List available subtitles in info panel."""
        def task():
            self.show_progress()
            self.disable_action_buttons()
            self.safe_after(0, lambda: self.update_status("Listing current subtitles..."))

            items = self.get_video_items()
            if not items:
                self.safe_after(0, lambda: self.update_status("No items selected"))
                self.hide_progress()
                self.enable_action_buttons()
                return

            # Clear and configure info panel
            self.safe_after(0, self.clear_info_panel)
            self.safe_after(0, lambda: self.info_panel_title.configure(text="📋 Current Subtitles"))
            self.safe_after(0, lambda: self.info_panel_action_btn.configure(text="Close", command=self.clear_info_panel))
            self.safe_after(0, lambda: self.info_frame.grid())

            row = 0
            for item in items:
                title = self._get_item_title(item)

                # Get actual file name from Plex
                actual_filename = "Unknown"
                try:
                    for media in item.media:
                        for part in media.parts:
                            if part.file:
                                actual_filename = os.path.basename(part.file)
                                break
                        if actual_filename != "Unknown":
                            break
                except:
                    pass

                # Create frame for this item
                def create_item_frame(t=title, fn=actual_filename, itm=item, r=row):
                    item_frame = ctk.CTkFrame(self.info_scroll, fg_color=("gray85", "gray25"))
                    item_frame.grid(row=r, column=0, sticky="ew", pady=(0, 10))
                    item_frame.grid_columnconfigure(0, weight=1)

                    # Title
                    ctk.CTkLabel(item_frame, text=t, font=ctk.CTkFont(weight="bold"),
                                anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))

                    # File name
                    ctk.CTkLabel(item_frame, text=f"File: {fn}",
                                font=ctk.CTkFont(size=11), text_color="gray",
                                anchor="w").grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

                    # Get subtitles
                    try:
                        has_subs = False
                        sub_row = 2
                        for media in itm.media:
                            for part in media.parts:
                                subs = part.subtitleStreams()
                                if subs:
                                    has_subs = True
                                    for sub in subs:
                                        selected = "✓" if sub.selected else "○"
                                        language = sub.language or "Unknown"
                                        codec = sub.codec or "?"
                                        forced = " [Forced]" if sub.forced else ""
                                        sdh = " [SDH]" if sub.hearingImpaired else ""

                                        # Get subtitle file name or title
                                        sub_detail = ""
                                        if hasattr(sub, 'title') and sub.title:
                                            sub_detail = f" - {sub.title}"
                                        elif hasattr(sub, 'key') and sub.key:
                                            # Extract filename from key path
                                            try:
                                                filename = sub.key.split('/')[-1]
                                                if filename:
                                                    sub_detail = f" - {filename}"
                                            except:
                                                pass

                                        sub_text = f"{selected} {language} ({codec}){forced}{sdh}{sub_detail}"
                                        text_color = ("green", "#2d7a2d") if sub.selected else ("gray60", "gray")

                                        ctk.CTkLabel(item_frame, text=sub_text,
                                                    font=ctk.CTkFont(size=11), text_color=text_color,
                                                    anchor="w").grid(row=sub_row, column=0, sticky="w", padx=20, pady=1)
                                        sub_row += 1

                        if not has_subs:
                            ctk.CTkLabel(item_frame, text="✗ No subtitles available",
                                        font=ctk.CTkFont(size=11), text_color=("red", "#8b0000"),
                                        anchor="w").grid(row=2, column=0, sticky="w", padx=20, pady=5)
                        else:
                            # Add padding
                            ctk.CTkLabel(item_frame, text="").grid(row=sub_row, column=0, pady=5)

                    except Exception as e:
                        ctk.CTkLabel(item_frame, text=f"✗ Error: {e}",
                                    font=ctk.CTkFont(size=11), text_color=("red", "#8b0000"),
                                    anchor="w").grid(row=2, column=0, sticky="w", padx=20, pady=5)

                self.safe_after(0, create_item_frame)
                row += 1

            self.safe_after(0, lambda: self.update_status(f"Listed subtitles for {len(items)} item(s)"))
            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

    def delete_subtitles(self):
        """Delete all subtitle streams from selected items."""
        items = self.get_video_items()
        if not items:
            self.update_status("No items selected")
            return

        # Show confirmation dialog for bulk operations
        num_items = len(items)
        if num_items >= 5:
            if not self.show_confirmation_dialog(
                "Delete Confirmation",
                f"About to delete all subtitles from {num_items} item(s).\n\nThis action cannot be undone. Continue?"
            ):
                self.update_status("Delete cancelled")
                return
        else:
            # Even for small number of items, confirm deletion
            if not self.show_confirmation_dialog(
                "Delete Confirmation",
                f"About to delete all subtitles from {num_items} item(s).\n\nThis action cannot be undone. Continue?"
            ):
                self.update_status("Delete cancelled")
                return

        def task():
            self.show_progress()
            self.disable_action_buttons()
            self.safe_after(0, lambda: self.update_status(f"Deleting subtitles from {num_items} item(s)..."))

            success_count = 0
            error_count = 0
            successful_items = []

            for item in items:
                if self._is_destroyed:
                    return

                title = self._get_item_title(item)
                try:
                    # Get all subtitle streams for this item
                    subtitles_deleted = False
                    for media in item.media:
                        for part in media.parts:
                            subs = part.subtitleStreams()
                            if subs:
                                # Try to remove each subtitle
                                for sub in subs:
                                    try:
                                        # Use removeSubtitles method from PlexAPI
                                        item.removeSubtitles(subtitleStream=sub)
                                        subtitles_deleted = True
                                    except Exception as sub_error:
                                        # Some subtitles (embedded) cannot be removed
                                        self.log(f"  Note: Could not remove {sub.language or 'unknown'} subtitle from {title}: {sub_error}")

                    if subtitles_deleted:
                        success_count += 1
                        successful_items.append(item)
                        self.log(f"  ✓ {title}")

                        # Reload item to update cache
                        try:
                            item.reload()
                            self.subtitle_status_cache[item.ratingKey] = False
                        except:
                            pass
                    else:
                        self.log(f"  ℹ {title} - No subtitles to delete or all are embedded")
                        error_count += 1

                except Exception as e:
                    self.log(f"  ✗ {title} - Error: {e}")
                    error_count += 1

            # Final status
            self.log(f"\nDeletion complete: {success_count} successful, {error_count} failed/no subtitles")
            self.safe_after(0, lambda: self.update_status(
                f"✓ Deleted subtitles from {success_count}/{num_items} item(s)"))

            if successful_items:
                self.safe_after(0, lambda: messagebox.showinfo(
                    "Complete",
                    f"Subtitle deletion finished!\n\n"
                    f"Successfully deleted: {success_count}\n"
                    f"Failed or no subtitles: {error_count}",
                    parent=self))

                # Refresh subtitle indicators
                self.safe_after(0, lambda: self.refresh_subtitle_indicators(successful_items))
            else:
                self.safe_after(0, lambda: messagebox.showwarning(
                    "No Changes",
                    f"No subtitles were deleted.\n\n"
                    f"Items may have no subtitles or only embedded subtitles (which cannot be removed).",
                    parent=self))

            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

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
        """Load application settings."""
        config = configparser.ConfigParser()
        config.read('config.ini')

        # === General Settings ===
        self.subtitle_save_method = config.get('General', 'subtitle_save_method', fallback='plex')
        self.default_language = config.get('General', 'default_language', fallback='English')
        self.appearance_mode = config.get('General', 'appearance_mode', fallback='dark')
        self.remember_last_library = config.getboolean('General', 'remember_last_library', fallback=True)
        self.last_library = config.get('General', 'last_library', fallback='')

        # === Subtitle Settings ===
        self.prefer_hearing_impaired = config.getboolean('Subtitles', 'prefer_hearing_impaired', fallback=False)
        self.prefer_forced = config.getboolean('Subtitles', 'prefer_forced', fallback=False)
        self.default_providers = config.get('Subtitles', 'default_providers', fallback='opensubtitles,podnapisi')
        self.search_timeout = config.getint('Subtitles', 'search_timeout', fallback=30)

        # === UI Settings ===
        self.show_log_on_startup = config.getboolean('UI', 'show_log_on_startup', fallback=False)
        self.default_subtitle_filter = config.get('UI', 'default_subtitle_filter', fallback='all')
        self.confirm_batch_operations = config.getboolean('UI', 'confirm_batch_operations', fallback=True)
        self.batch_operation_threshold = config.getint('UI', 'batch_operation_threshold', fallback=10)

        # === Advanced Settings ===
        self.concurrent_downloads = config.getint('Advanced', 'concurrent_downloads', fallback=3)
        self.enable_debug_logging = config.getboolean('Advanced', 'enable_debug_logging', fallback=False)

        # Apply settings
        ctk.set_appearance_mode(self.appearance_mode)

        # Set logging level based on debug setting
        if self.enable_debug_logging:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

    def save_settings(self):
        """Save application settings."""
        config = configparser.ConfigParser()

        # Read existing config to preserve other sections
        config.read('config.ini')

        # === General Settings ===
        if not config.has_section('General'):
            config.add_section('General')
        config.set('General', 'subtitle_save_method', self.subtitle_save_method)
        config.set('General', 'default_language', self.default_language)
        config.set('General', 'appearance_mode', self.appearance_mode)
        config.set('General', 'remember_last_library', str(self.remember_last_library))
        config.set('General', 'last_library', self.last_library if hasattr(self, 'last_library') else '')

        # === Subtitle Settings ===
        if not config.has_section('Subtitles'):
            config.add_section('Subtitles')
        config.set('Subtitles', 'prefer_hearing_impaired', str(self.prefer_hearing_impaired))
        config.set('Subtitles', 'prefer_forced', str(self.prefer_forced))
        config.set('Subtitles', 'default_providers', self.default_providers)
        config.set('Subtitles', 'search_timeout', str(self.search_timeout))

        # === UI Settings ===
        if not config.has_section('UI'):
            config.add_section('UI')
        config.set('UI', 'show_log_on_startup', str(self.show_log_on_startup))
        config.set('UI', 'default_subtitle_filter', self.default_subtitle_filter)
        config.set('UI', 'confirm_batch_operations', str(self.confirm_batch_operations))
        config.set('UI', 'batch_operation_threshold', str(self.batch_operation_threshold))

        # === Advanced Settings ===
        if not config.has_section('Advanced'):
            config.add_section('Advanced')
        config.set('Advanced', 'concurrent_downloads', str(self.concurrent_downloads))
        config.set('Advanced', 'enable_debug_logging', str(self.enable_debug_logging))

        # Write to file
        with open('config.ini', 'w') as f:
            config.write(f)

        # Apply runtime settings changes
        ctk.set_appearance_mode(self.appearance_mode)
        if self.enable_debug_logging:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)

    def open_settings(self):
        """Open comprehensive settings dialog with tabs."""
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("PlexSubSetter Settings")
        settings_window.geometry("800x650")
        settings_window.transient(self)
        settings_window.grab_set()

        # Center window
        settings_window.update_idletasks()
        x = (settings_window.winfo_screenwidth() // 2) - (800 // 2)
        y = (settings_window.winfo_screenheight() // 2) - (650 // 2)
        settings_window.geometry(f"800x650+{x}+{y}")

        # Main container
        main_frame = ctk.CTkFrame(settings_window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(main_frame, text="⚙ Settings",
                    font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", pady=(0, 15))

        # Create tabview
        tabview = ctk.CTkTabview(main_frame)
        tabview.pack(fill="both", expand=True, pady=(0, 15))

        # Create tabs
        general_tab = tabview.add("General")
        subtitles_tab = tabview.add("Subtitles")
        ui_tab = tabview.add("UI/Behavior")
        advanced_tab = tabview.add("Advanced")

        # Store settings in variables
        settings_vars = {}

        # ==================== GENERAL TAB ====================
        general_scroll = ctk.CTkScrollableFrame(general_tab)
        general_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Default Language
        ctk.CTkLabel(general_scroll, text="Default Subtitle Language",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['default_language'] = ctk.StringVar(value=self.default_language)
        lang_combo = ctk.CTkComboBox(general_scroll, values=list(SEARCH_LANGUAGES.keys()),
                                     variable=settings_vars['default_language'], state="readonly")
        lang_combo.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(general_scroll, text="Language used when searching for subtitles",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Appearance Mode
        ctk.CTkLabel(general_scroll, text="Appearance Theme",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['appearance_mode'] = ctk.StringVar(value=self.appearance_mode)
        appearance_frame = ctk.CTkFrame(general_scroll, fg_color="transparent")
        appearance_frame.pack(fill="x", pady=(0, 5))
        for mode in ["dark", "light", "system"]:
            ctk.CTkRadioButton(appearance_frame, text=mode.capitalize(),
                              variable=settings_vars['appearance_mode'],
                              value=mode).pack(side="left", padx=(0, 20))
        ctk.CTkLabel(general_scroll, text="Choose the color theme for the application",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Remember Last Library
        settings_vars['remember_last_library'] = ctk.BooleanVar(value=self.remember_last_library)
        ctk.CTkCheckBox(general_scroll, text="Remember last selected library",
                       variable=settings_vars['remember_last_library']).pack(anchor="w", pady=(5, 5))
        ctk.CTkLabel(general_scroll, text="Automatically select the last used library when opening the app",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # ==================== SUBTITLES TAB ====================
        subtitles_scroll = ctk.CTkScrollableFrame(subtitles_tab)
        subtitles_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Subtitle Save Method
        ctk.CTkLabel(subtitles_scroll, text="Subtitle Save Method",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['subtitle_save_method'] = ctk.StringVar(value=self.subtitle_save_method)

        save_method_frame = ctk.CTkFrame(subtitles_scroll, fg_color=("gray85", "gray20"))
        save_method_frame.pack(fill="x", pady=(0, 5))

        ctk.CTkRadioButton(save_method_frame, text="Upload to Plex (Recommended)",
                          variable=settings_vars['subtitle_save_method'],
                          value="plex").pack(anchor="w", padx=15, pady=(10, 5))
        ctk.CTkLabel(save_method_frame,
                    text="  • Subtitles uploaded to Plex's internal database\n"
                         "  • Works with remote servers\n"
                         "  • Subtitles survive if video files move",
                    font=ctk.CTkFont(size=11), text_color="gray",
                    justify="left").pack(anchor="w", padx=30, pady=(0, 10))

        ctk.CTkRadioButton(save_method_frame, text="Save next to video file",
                          variable=settings_vars['subtitle_save_method'],
                          value="file").pack(anchor="w", padx=15, pady=(5, 5))
        ctk.CTkLabel(save_method_frame,
                    text="  • Subtitles saved alongside video files\n"
                         "  • Requires local or network file access\n"
                         "  • Plex auto-detects on next scan",
                    font=ctk.CTkFont(size=11), text_color="gray",
                    justify="left").pack(anchor="w", padx=30, pady=(0, 10))

        # Subtitle Preferences
        ctk.CTkLabel(subtitles_scroll, text="Subtitle Preferences",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(15, 5))

        settings_vars['prefer_hearing_impaired'] = ctk.BooleanVar(value=self.prefer_hearing_impaired)
        ctk.CTkCheckBox(subtitles_scroll, text="Prefer hearing impaired (SDH) subtitles",
                       variable=settings_vars['prefer_hearing_impaired']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(subtitles_scroll, text="Prioritize subtitles with sound descriptions",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 10))

        settings_vars['prefer_forced'] = ctk.BooleanVar(value=self.prefer_forced)
        ctk.CTkCheckBox(subtitles_scroll, text="Prefer forced subtitles",
                       variable=settings_vars['prefer_forced']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(subtitles_scroll, text="Subtitles only for foreign language parts",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 15))

        # Default Providers
        ctk.CTkLabel(subtitles_scroll, text="Default Subtitle Providers",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['default_providers'] = ctk.StringVar(value=self.default_providers)
        providers_entry = ctk.CTkEntry(subtitles_scroll, textvariable=settings_vars['default_providers'])
        providers_entry.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(subtitles_scroll,
                    text="Comma-separated list: opensubtitles, podnapisi, tvsubtitles, addic7ed",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Search Timeout
        ctk.CTkLabel(subtitles_scroll, text="Search Timeout (seconds)",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['search_timeout'] = ctk.IntVar(value=self.search_timeout)
        timeout_slider = ctk.CTkSlider(subtitles_scroll, from_=10, to=120,
                                       variable=settings_vars['search_timeout'],
                                       number_of_steps=22)
        timeout_slider.pack(fill="x", pady=(0, 5))
        timeout_label = ctk.CTkLabel(subtitles_scroll, text=f"{self.search_timeout} seconds")
        timeout_label.pack(anchor="w", pady=(0, 5))

        def update_timeout_label(*args):
            timeout_label.configure(text=f"{settings_vars['search_timeout'].get()} seconds")
        settings_vars['search_timeout'].trace_add("write", update_timeout_label)

        ctk.CTkLabel(subtitles_scroll, text="Maximum time to wait for subtitle search results",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # ==================== UI/BEHAVIOR TAB ====================
        ui_scroll = ctk.CTkScrollableFrame(ui_tab)
        ui_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Show Log on Startup
        ctk.CTkLabel(ui_scroll, text="Startup Behavior",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['show_log_on_startup'] = ctk.BooleanVar(value=self.show_log_on_startup)
        ctk.CTkCheckBox(ui_scroll, text="Show log panel on startup",
                       variable=settings_vars['show_log_on_startup']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(ui_scroll, text="Display the activity log when the application starts",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 15))

        # Default Subtitle Filter
        ctk.CTkLabel(ui_scroll, text="Default Subtitle Filter",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['default_subtitle_filter'] = ctk.StringVar(value=self.default_subtitle_filter)
        filter_frame = ctk.CTkFrame(ui_scroll, fg_color="transparent")
        filter_frame.pack(fill="x", pady=(0, 5))
        for filter_opt in ["all", "missing", "has"]:
            ctk.CTkRadioButton(filter_frame, text=filter_opt.capitalize(),
                              variable=settings_vars['default_subtitle_filter'],
                              value=filter_opt).pack(side="left", padx=(0, 15))
        ctk.CTkLabel(ui_scroll, text="Default filter when viewing movie libraries",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Batch Operation Confirmations
        ctk.CTkLabel(ui_scroll, text="Batch Operations",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['confirm_batch_operations'] = ctk.BooleanVar(value=self.confirm_batch_operations)
        ctk.CTkCheckBox(ui_scroll, text="Confirm before batch operations",
                       variable=settings_vars['confirm_batch_operations']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(ui_scroll, text="Show confirmation dialog before processing multiple items",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 10))

        # Batch Operation Threshold
        ctk.CTkLabel(ui_scroll, text="Batch operation threshold:",
                    font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(5, 5))
        settings_vars['batch_operation_threshold'] = ctk.IntVar(value=self.batch_operation_threshold)
        threshold_slider = ctk.CTkSlider(ui_scroll, from_=5, to=50,
                                        variable=settings_vars['batch_operation_threshold'],
                                        number_of_steps=9)
        threshold_slider.pack(fill="x", pady=(0, 5))
        threshold_label = ctk.CTkLabel(ui_scroll, text=f"{self.batch_operation_threshold} items")
        threshold_label.pack(anchor="w", pady=(0, 5))

        def update_threshold_label(*args):
            threshold_label.configure(text=f"{settings_vars['batch_operation_threshold'].get()} items")
        settings_vars['batch_operation_threshold'].trace_add("write", update_threshold_label)

        ctk.CTkLabel(ui_scroll, text="Show warning when operating on this many items or more",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # ==================== ADVANCED TAB ====================
        advanced_scroll = ctk.CTkScrollableFrame(advanced_tab)
        advanced_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(advanced_scroll, text="⚠ Advanced Settings",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color="#e5a00d").pack(anchor="w", pady=(5, 5))
        ctk.CTkLabel(advanced_scroll, text="Modify these settings only if you know what you're doing",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Concurrent Downloads
        ctk.CTkLabel(advanced_scroll, text="Concurrent Downloads",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(5, 5))
        settings_vars['concurrent_downloads'] = ctk.IntVar(value=self.concurrent_downloads)
        concurrent_slider = ctk.CTkSlider(advanced_scroll, from_=1, to=10,
                                         variable=settings_vars['concurrent_downloads'],
                                         number_of_steps=9)
        concurrent_slider.pack(fill="x", pady=(0, 5))
        concurrent_label = ctk.CTkLabel(advanced_scroll, text=f"{self.concurrent_downloads} downloads")
        concurrent_label.pack(anchor="w", pady=(0, 5))

        def update_concurrent_label(*args):
            concurrent_label.configure(text=f"{settings_vars['concurrent_downloads'].get()} downloads")
        settings_vars['concurrent_downloads'].trace_add("write", update_concurrent_label)

        ctk.CTkLabel(advanced_scroll, text="Maximum number of simultaneous subtitle downloads",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", pady=(0, 15))

        # Debug Logging
        settings_vars['enable_debug_logging'] = ctk.BooleanVar(value=self.enable_debug_logging)
        ctk.CTkCheckBox(advanced_scroll, text="Enable debug logging",
                       variable=settings_vars['enable_debug_logging']).pack(anchor="w", pady=(5, 2))
        ctk.CTkLabel(advanced_scroll, text="Write detailed debug information to log files (increases log size)",
                    font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w", padx=25, pady=(0, 15))

        # Log file location
        ctk.CTkLabel(advanced_scroll, text="Current log file:",
                    font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(10, 5))
        log_path_frame = ctk.CTkFrame(advanced_scroll, fg_color=("gray85", "gray20"))
        log_path_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(log_path_frame, text=self.current_log_file,
                    font=ctk.CTkFont(size=10, family="Courier"),
                    text_color="gray").pack(anchor="w", padx=10, pady=10)

        # ==================== BUTTONS ====================
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))

        def save_and_close():
            # Apply all settings from variables
            self.subtitle_save_method = settings_vars['subtitle_save_method'].get()
            self.default_language = settings_vars['default_language'].get()
            self.appearance_mode = settings_vars['appearance_mode'].get()
            self.remember_last_library = settings_vars['remember_last_library'].get()
            self.prefer_hearing_impaired = settings_vars['prefer_hearing_impaired'].get()
            self.prefer_forced = settings_vars['prefer_forced'].get()
            self.default_providers = settings_vars['default_providers'].get()
            self.search_timeout = settings_vars['search_timeout'].get()
            self.show_log_on_startup = settings_vars['show_log_on_startup'].get()
            self.default_subtitle_filter = settings_vars['default_subtitle_filter'].get()
            self.confirm_batch_operations = settings_vars['confirm_batch_operations'].get()
            self.batch_operation_threshold = settings_vars['batch_operation_threshold'].get()
            self.concurrent_downloads = settings_vars['concurrent_downloads'].get()
            self.enable_debug_logging = settings_vars['enable_debug_logging'].get()

            # Save to config file
            self.save_settings()

            self.update_status("Settings saved successfully")
            self.log("Settings saved and applied", "info")
            settings_window.destroy()

        def reset_to_defaults():
            if messagebox.askyesno("Reset Settings", "Reset all settings to default values?", parent=settings_window):
                settings_vars['subtitle_save_method'].set('plex')
                settings_vars['default_language'].set('English')
                settings_vars['appearance_mode'].set('dark')
                settings_vars['remember_last_library'].set(True)
                settings_vars['prefer_hearing_impaired'].set(False)
                settings_vars['prefer_forced'].set(False)
                settings_vars['default_providers'].set('opensubtitles,podnapisi')
                settings_vars['search_timeout'].set(30)
                settings_vars['show_log_on_startup'].set(False)
                settings_vars['default_subtitle_filter'].set('all')
                settings_vars['confirm_batch_operations'].set(True)
                settings_vars['batch_operation_threshold'].set(10)
                settings_vars['concurrent_downloads'].set(3)
                settings_vars['enable_debug_logging'].set(False)

        reset_btn = ctk.CTkButton(button_frame, text="Reset to Defaults",
                                  command=reset_to_defaults,
                                  width=130, fg_color="transparent", border_width=2,
                                  border_color=("gray60", "gray40"),
                                  text_color=("gray10", "gray90"))
        reset_btn.pack(side="left")

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel",
                                   command=settings_window.destroy,
                                   width=100, fg_color="transparent", border_width=2,
                                   text_color=("gray10", "gray90"))
        cancel_btn.pack(side="right", padx=(10, 0))

        save_btn = ctk.CTkButton(button_frame, text="Save Settings",
                                command=save_and_close,
                                width=120)
        save_btn.pack(side="right")


