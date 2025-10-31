#!/usr/bin/env python3
"""
PlexSubSetter GUI - Mass Subtitle Finder and Setter for Plex
A modern graphical tool to search, download, and set subtitles for your Plex media library.
"""

__version__ = "1.0.0"
__author__ = "primetime43"
__repo__ = "https://github.com/primetime43/PlexSubSetter"

import customtkinter as ctk
from tkinter import messagebox
import threading
import configparser
import os
import sys
import tempfile
import webbrowser
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from plexapi.server import PlexServer
from plexapi.video import Movie, Episode, Show, Season
from subliminal import region, save_subtitles, download_best_subtitles, download_subtitles
from subliminal.video import Episode as SubliminalEpisode, Movie as SubliminalMovie
from subliminal.providers.opensubtitles import OpenSubtitlesProvider
from babelfish import Language


# Set appearance and theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# Language mappings
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


class LoginFrame(ctk.CTkFrame):
    """Login frame for Plex OAuth authentication."""

    def __init__(self, master, on_login_success):
        super().__init__(master)
        self.on_login_success = on_login_success
        self.pin_login = None

        # Configure grid
        self.grid_columnconfigure(0, weight=1)

        # Title
        title = ctk.CTkLabel(self, text="PlexSubSetter", font=ctk.CTkFont(size=32, weight="bold"))
        title.grid(row=0, column=0, pady=(60, 10), padx=20)

        subtitle = ctk.CTkLabel(self, text="Mass Subtitle Manager for Plex",
                               font=ctk.CTkFont(size=14), text_color="gray")
        subtitle.grid(row=1, column=0, pady=(0, 50), padx=20)

        # Login container
        login_frame = ctk.CTkFrame(self, fg_color="transparent")
        login_frame.grid(row=2, column=0, pady=20, padx=40, sticky="ew")
        login_frame.grid_columnconfigure(0, weight=1)

        # Plex logo/icon text
        icon_label = ctk.CTkLabel(login_frame, text="🎬", font=ctk.CTkFont(size=48))
        icon_label.grid(row=0, column=0, pady=(0, 20))

        # Sign in button
        self.login_btn = ctk.CTkButton(
            login_frame,
            text="Sign in with Plex",
            command=self.start_oauth_login,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#e5a00d",
            hover_color="#cc8f0c"
        )
        self.login_btn.grid(row=1, column=0, pady=(0, 15), sticky="ew", padx=60)

        # Status label
        self.status_label = ctk.CTkLabel(login_frame, text="", wraplength=400)
        self.status_label.grid(row=2, column=0, pady=(15, 0))

        # Info label
        info_text = "You'll be redirected to Plex.tv to sign in securely.\nNo credentials are stored in this application."
        info_label = ctk.CTkLabel(self, text=info_text, font=ctk.CTkFont(size=11),
                                 text_color="gray", wraplength=400)
        info_label.grid(row=3, column=0, pady=(40, 20))

        # Footer with version, author, and repo link
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=4, column=0, pady=(10, 40))

        version_label = ctk.CTkLabel(footer_frame, text=f"Version {__version__}",
                                     font=ctk.CTkFont(size=10), text_color="gray")
        version_label.pack(pady=(0, 5))

        author_label = ctk.CTkLabel(footer_frame, text=f"Created by {__author__}",
                                    font=ctk.CTkFont(size=10), text_color="gray")
        author_label.pack(pady=(0, 5))

        # Clickable repository link
        repo_label = ctk.CTkLabel(footer_frame, text="🔗 View on GitHub",
                                  font=ctk.CTkFont(size=10, underline=True),
                                  text_color="#58a6ff", cursor="hand2")
        repo_label.pack()
        repo_label.bind("<Button-1>", lambda e: webbrowser.open(__repo__))

    def start_oauth_login(self):
        """Start the OAuth login process."""
        self.login_btn.configure(state="disabled", text="Opening browser...")
        self.status_label.configure(text="Opening your browser for authentication...", text_color="yellow")

        def oauth_thread():
            try:
                # Create PIN login with OAuth
                self.pin_login = MyPlexPinLogin(oauth=True)

                # Get OAuth URL
                oauth_url = self.pin_login.oauthUrl()

                # Update UI
                self.after(0, lambda: self.status_label.configure(
                    text="✓ Browser opened! Please sign in to Plex...\n\nWaiting for authentication...",
                    text_color="#e5a00d"
                ))
                self.after(0, lambda: self.login_btn.configure(text="Waiting for sign in..."))

                # Open browser
                webbrowser.open(oauth_url)

                # Wait for login with callback
                def on_login(token):
                    if token:
                        try:
                            account = MyPlexAccount(token=token)
                            self.after(0, lambda: self.on_login_success(account))
                        except Exception as e:
                            self.after(0, lambda: self.handle_error(f"Failed to get account: {e}"))
                    else:
                        self.after(0, lambda: self.handle_error("Login failed or timed out"))

                # Run with timeout of 5 minutes
                self.pin_login.run(callback=on_login, timeout=300)

            except Exception as e:
                self.after(0, lambda: self.handle_error(str(e)))

        threading.Thread(target=oauth_thread, daemon=True).start()

    def handle_error(self, error_msg):
        """Handle login errors."""
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            error_msg = "Login timed out. Please try again."
        elif "Network" in error_msg or "Connection" in error_msg:
            error_msg = "Network error. Please check your connection."

        self.status_label.configure(text=f"✗ {error_msg}", text_color="red")
        self.login_btn.configure(state="normal", text="Sign in with Plex")


class ServerSelectionFrame(ctk.CTkFrame):
    """Server selection frame."""

    def __init__(self, master, account, on_server_selected, on_logout):
        super().__init__(master)
        self.account = account
        self.on_server_selected = on_server_selected
        self.on_logout = on_logout

        # Configure grid
        self.grid_columnconfigure(0, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, pady=(20, 10), padx=20, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(header_frame, text=f"Welcome, {account.username}!",
                            font=ctk.CTkFont(size=20, weight="bold"))
        title.grid(row=0, column=0, sticky="w")

        logout_btn = ctk.CTkButton(header_frame, text="Logout", command=on_logout,
                                   width=100, fg_color="transparent", border_width=2)
        logout_btn.grid(row=0, column=1, sticky="e")

        # Subtitle
        subtitle = ctk.CTkLabel(self, text="Select a Plex server to manage subtitles",
                               font=ctk.CTkFont(size=14))
        subtitle.grid(row=1, column=0, pady=(0, 20), padx=20)

        # Servers container
        servers_frame = ctk.CTkScrollableFrame(self, label_text="Available Servers")
        servers_frame.grid(row=2, column=0, pady=10, padx=40, sticky="nsew")
        servers_frame.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Status label
        self.status_label = ctk.CTkLabel(self, text="Loading servers...", text_color="yellow")
        self.status_label.grid(row=3, column=0, pady=10)

        # Load servers
        self.load_servers(servers_frame)

    def load_servers(self, container):
        """Load available Plex servers."""
        def load_thread():
            try:
                resources = self.account.resources()
                servers = [r for r in resources if r.product == 'Plex Media Server']

                if not servers:
                    self.after(0, lambda: self.status_label.configure(
                        text="No servers found on your account", text_color="red"))
                    return

                self.after(0, lambda: self.status_label.configure(text=""))

                # Separate servers into online and offline
                online_servers = [s for s in servers if s.presence]
                offline_servers = [s for s in servers if not s.presence]

                # Combine with online servers first, then offline
                sorted_servers = online_servers + offline_servers

                for i, resource in enumerate(sorted_servers):
                    def create_server_button(res, row_index):
                        # Server card
                        card = ctk.CTkFrame(container)
                        card.grid(row=row_index, column=0, pady=5, padx=5, sticky="ew")
                        card.grid_columnconfigure(0, weight=1)

                        # Server info
                        name_label = ctk.CTkLabel(card, text=res.name,
                                                 font=ctk.CTkFont(size=16, weight="bold"),
                                                 anchor="w")
                        name_label.grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))

                        # Status and presence
                        status = "🟢 Online" if res.presence else "🔴 Offline"
                        status_color = "#2ecc71" if res.presence else "#e74c3c"  # Green if online, red if offline
                        status_label = ctk.CTkLabel(card, text=status, anchor="w", text_color=status_color)
                        status_label.grid(row=1, column=0, sticky="w", padx=15, pady=(0, 5))

                        # Platform info
                        platform_text = f"Platform: {res.platform} | Version: {res.platformVersion}"
                        platform_label = ctk.CTkLabel(card, text=platform_text, anchor="w",
                                                     text_color="gray", font=ctk.CTkFont(size=11))
                        platform_label.grid(row=2, column=0, sticky="w", padx=15, pady=(0, 15))

                        # Connect button
                        connect_btn = ctk.CTkButton(card, text="Connect",
                                                   command=lambda: self.connect_to_server(res),
                                                   width=120)
                        connect_btn.grid(row=0, column=1, rowspan=3, padx=15, pady=10)

                    self.after(0, lambda r=resource, idx=i: create_server_button(r, idx))

            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"Error loading servers: {e}", text_color="red"))

        threading.Thread(target=load_thread, daemon=True).start()

    def connect_to_server(self, resource):
        """Connect to selected server."""
        self.status_label.configure(text=f"Connecting to {resource.name}...", text_color="yellow")

        def connect_thread():
            try:
                plex = resource.connect()
                self.after(0, lambda: self.on_server_selected(plex))
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"Failed to connect: {e}", text_color="red"))

        threading.Thread(target=connect_thread, daemon=True).start()


class MainAppFrame(ctk.CTkFrame):
    """Main application frame for subtitle management."""

    def __init__(self, master, plex, on_logout):
        super().__init__(master, fg_color="transparent")
        self.plex = plex
        self.on_logout = on_logout
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
        browser_panel = ctk.CTkFrame(self)
        browser_panel.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        browser_panel.grid_columnconfigure(0, weight=1)
        browser_panel.grid_rowconfigure(5, weight=1)  # Browser scroll can expand

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
                                        fg_color="transparent", hover_color="#404040")
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
                                           height=24, fg_color="#1f538d", hover_color="#1a4472")
        self.filter_all_btn.grid(row=1, column=0, padx=(0, 3), sticky="ew")

        self.filter_missing_btn = ctk.CTkButton(self.filter_btn_frame, text="Missing",
                                               command=lambda: self.set_subtitle_filter("missing"),
                                               height=24, fg_color="transparent", border_width=1,
                                               border_color="gray50")
        self.filter_missing_btn.grid(row=1, column=1, padx=(0, 3), sticky="ew")

        self.filter_has_btn = ctk.CTkButton(self.filter_btn_frame, text="Has Subs",
                                           command=lambda: self.set_subtitle_filter("has"),
                                           height=24, fg_color="transparent", border_width=1,
                                           border_color="gray50")
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
                                           fg_color="transparent", border_width=1)
        self.select_all_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.clear_selection_btn = ctk.CTkButton(btn_frame, text="Clear", height=24,
                                                command=self.clear_selection,
                                                fg_color="transparent", border_width=1)
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
                                    width=100, fg_color="transparent", border_width=2)
        settings_btn.grid(row=0, column=1, padx=(15, 5), pady=15)

        logout_btn = ctk.CTkButton(header_frame, text="Change Server", command=self.on_logout,
                                   width=120, fg_color="transparent", border_width=2)
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
                                         fg_color="#1f538d", hover_color="#1a4472",
                                         state="disabled")
        self.download_btn.grid(row=0, column=1, padx=5, pady=15, sticky="ew")

        self.list_btn = ctk.CTkButton(actions_frame, text="📋 List Current",
                                     command=self.list_subtitles, height=40,
                                     fg_color="#6b4f9d", hover_color="#553d7d",
                                     state="disabled")
        self.list_btn.grid(row=0, column=2, padx=5, pady=15, sticky="ew")

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
                                           border_width=1, anchor="w")
        self.log_toggle_btn.grid(row=0, column=0, sticky="w")

        clear_btn = ctk.CTkButton(log_header, text="Clear", command=self.clear_log,
                                 width=60, height=24, fg_color="transparent")
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

    def log(self, message):
        """Add message to log."""
        self.output_text.configure(state="normal")
        self.output_text.insert("end", message + "\n")
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

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
        """Refresh library list."""
        self.log("Fetching libraries...")

        def refresh_thread():
            if self._is_destroyed:
                return

            try:
                self.libraries = []
                for section in self.plex.library.sections():
                    self.libraries.append(section)
                    self.safe_after(0, lambda s=section: self.log(f"  Found: {s.title} (Type: {s.type})"))

                lib_names = [lib.title for lib in self.libraries]
                self.safe_after(0, lambda: self.library_combo.configure(values=lib_names))
                if lib_names:
                    self.safe_after(0, lambda: self.library_combo.set(lib_names[0]))
                    self.safe_after(0, lambda: self.load_library_content())

                self.safe_after(0, lambda: self.log(f"✓ Loaded {len(self.libraries)} libraries\n"))

            except Exception as e:
                self.safe_after(0, lambda: self.log(f"✗ Error fetching libraries: {e}\n"))

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
            self.filter_all_btn.configure(fg_color="#1f538d", border_width=0)
            self.filter_missing_btn.configure(fg_color="transparent", border_width=1)
            self.filter_has_btn.configure(fg_color="transparent", border_width=1)
        elif filter_type == "missing":
            self.filter_all_btn.configure(fg_color="transparent", border_width=1)
            self.filter_missing_btn.configure(fg_color="#8b0000", border_width=0)
            self.filter_has_btn.configure(fg_color="transparent", border_width=1)
        elif filter_type == "has":
            self.filter_all_btn.configure(fg_color="transparent", border_width=1)
            self.filter_missing_btn.configure(fg_color="transparent", border_width=1)
            self.filter_has_btn.configure(fg_color="#2d7a2d", border_width=0)

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
        if not library_name:
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
                self.safe_after(0, lambda: self.log(f"✗ Error loading library: {e}\n"))

        threading.Thread(target=load_thread, daemon=True).start()

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

                cb = ctk.CTkCheckBox(frame, text=f"{movie.title} ({movie.year})",
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
                            status_color = "#2d7a2d" if has_subs else "#8b0000"
                            self.safe_after(0, lambda f=frame, i=status_icon, c=status_color:
                                           f.status_label.configure(text=i, text_color=c))
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
                                           command=lambda s=show, f=show_frame, v=expand_var: self.toggle_show(s, f, v))
                expand_btn.pack(side="left", padx=(0, 5))

                show_cb = ctk.CTkCheckBox(show_inner, text=f"{show.title}",
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

                ep_cb = ctk.CTkCheckBox(ep_frame,
                                       text=f"E{episode.index:02d} - {episode.title}",
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
                                         fg_color="transparent", border_width=1)
                prev_btn.pack(side="left", padx=2)

                page_label = ctk.CTkLabel(pagination_frame,
                                         text=f"{page_num}/{total_pages}",
                                         font=ctk.CTkFont(size=10))
                page_label.pack(side="left", expand=True)

                next_btn = ctk.CTkButton(pagination_frame, text="▶",
                                         width=60, height=24,
                                         command=lambda: load_episode_page(page_num + 1),
                                         state="normal" if page_num < total_pages else "disabled",
                                         fg_color="transparent", border_width=1)
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
                            status_color = "#2d7a2d" if has_subs else "#8b0000"
                            self.safe_after(0, lambda f=frame, i=status_icon, c=status_color:
                                           f.status_label.configure(text=i, text_color=c))
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

            item = frame.item_obj
            has_subs = self.check_has_subtitles(item, force_refresh=True)

            # Update indicator
            status_icon = "✓" if has_subs else "✗"
            status_color = "#2d7a2d" if has_subs else "#8b0000"
            frame.status_label.configure(text=status_icon, text_color=status_color)

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
        def task():
            self.show_progress()
            self.disable_action_buttons()

            items = self.get_video_items()
            if not items:
                self.safe_after(0, lambda: self.update_status("No items selected"))
                self.hide_progress()
                self.enable_action_buttons()
                return

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
        def task():
            self.show_progress()
            self.disable_action_buttons()

            if not self.search_results:
                self.safe_after(0, lambda: self.update_status("No search results - Search first"))
                self.hide_progress()
                self.enable_action_buttons()
                return

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
                    self.log(f"Download error for {title}: {e}")

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
                                        text_color = "#2d7a2d" if sub.selected else "gray"

                                        ctk.CTkLabel(item_frame, text=sub_text,
                                                    font=ctk.CTkFont(size=11), text_color=text_color,
                                                    anchor="w").grid(row=sub_row, column=0, sticky="w", padx=20, pady=1)
                                        sub_row += 1

                        if not has_subs:
                            ctk.CTkLabel(item_frame, text="✗ No subtitles available",
                                        font=ctk.CTkFont(size=11), text_color="#8b0000",
                                        anchor="w").grid(row=2, column=0, sticky="w", padx=20, pady=5)
                        else:
                            # Add padding
                            ctk.CTkLabel(item_frame, text="").grid(row=sub_row, column=0, pady=5)

                    except Exception as e:
                        ctk.CTkLabel(item_frame, text=f"✗ Error: {e}",
                                    font=ctk.CTkFont(size=11), text_color="#8b0000",
                                    anchor="w").grid(row=2, column=0, sticky="w", padx=20, pady=5)

                self.safe_after(0, create_item_frame)
                row += 1

            self.safe_after(0, lambda: self.update_status(f"Listed subtitles for {len(items)} item(s)"))
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
        self.refresh_browser_btn.configure(state="disabled")

    def enable_action_buttons(self):
        """Enable action buttons if items selected."""
        state = "normal" if self.selected_items else "disabled"
        self.search_btn.configure(state=state)
        self.list_btn.configure(state=state)

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

    def load_settings(self):
        """Load application settings."""
        config = configparser.ConfigParser()
        config.read('config.ini')

        # Subtitle save method: 'plex' or 'file'
        self.subtitle_save_method = config.get('Settings', 'subtitle_save_method', fallback='plex')

    def save_settings(self):
        """Save application settings."""
        config = configparser.ConfigParser()

        # Read existing config to preserve other sections
        config.read('config.ini')

        # Create Settings section if it doesn't exist
        if not config.has_section('Settings'):
            config.add_section('Settings')

        # Save subtitle save method
        config.set('Settings', 'subtitle_save_method', self.subtitle_save_method)

        # Write to file
        with open('config.ini', 'w') as f:
            config.write(f)

    def open_settings(self):
        """Open settings dialog."""
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Settings")
        settings_window.geometry("650x500")
        settings_window.transient(self)
        settings_window.grab_set()

        # Center window
        settings_window.update_idletasks()
        x = (settings_window.winfo_screenwidth() // 2) - (650 // 2)
        y = (settings_window.winfo_screenheight() // 2) - (500 // 2)
        settings_window.geometry(f"650x500+{x}+{y}")

        # Main container
        main_frame = ctk.CTkFrame(settings_window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        ctk.CTkLabel(main_frame, text="⚙ Settings",
                    font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", pady=(0, 20))

        # === SUBTITLE SAVE METHOD ===
        save_method_frame = ctk.CTkFrame(main_frame, fg_color=("gray85", "gray25"))
        save_method_frame.pack(fill="x", pady=(0, 15))
        save_method_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(save_method_frame, text="Subtitle Save Method",
                    font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=15, pady=(15, 5))

        # Radio buttons for save method
        save_method_var = ctk.StringVar(value=self.subtitle_save_method)

        # Option 1: Upload to Plex
        plex_radio = ctk.CTkRadioButton(
            save_method_frame,
            text="Upload to Plex (Default)",
            variable=save_method_var,
            value="plex"
        )
        plex_radio.grid(row=1, column=0, sticky="w", padx=20, pady=(10, 5))

        plex_desc = ctk.CTkLabel(
            save_method_frame,
            text="• Subtitles are uploaded to Plex's internal database\n"
                 "• Works with remote Plex servers (no file access needed)\n"
                 "• Subtitles survive even if video files move\n"
                 "• Subtitles stored in Plex's Metadata directory",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left"
        )
        plex_desc.grid(row=2, column=0, sticky="w", padx=40, pady=(0, 10))

        # Show Plex metadata path
        try:
            if sys.platform.startswith('win'):
                plex_path = os.path.expandvars("%LOCALAPPDATA%\\Plex Media Server\\Media\\localhost")
            elif sys.platform == 'darwin':
                plex_path = os.path.expanduser("~/Library/Application Support/Plex Media Server/Media/localhost")
            else:
                plex_path = "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Media/localhost"

            plex_path_label = ctk.CTkLabel(
                save_method_frame,
                text=f"  Path: {plex_path}",
                font=ctk.CTkFont(size=10, family="Courier"),
                text_color="#e5a00d"
            )
            plex_path_label.grid(row=3, column=0, sticky="w", padx=40, pady=(0, 15))
        except:
            pass

        # Option 2: Save next to video file
        file_radio = ctk.CTkRadioButton(
            save_method_frame,
            text="Save next to video file",
            variable=save_method_var,
            value="file"
        )
        file_radio.grid(row=4, column=0, sticky="w", padx=20, pady=(5, 5))

        file_desc = ctk.CTkLabel(
            save_method_frame,
            text="• Subtitles saved in same directory as video files\n"
                 "• Standard naming: VideoName.en.srt, VideoName.es.srt, etc.\n"
                 "• Plex will auto-detect subtitles on next scan",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left"
        )
        file_desc.grid(row=5, column=0, sticky="w", padx=40, pady=(0, 5))

        # Warning note about network requirement
        file_warning = ctk.CTkLabel(
            save_method_frame,
            text="⚠ Note: Only works with local Plex servers or network-accessible file systems.\n"
                 "   Will not work with remote Plex servers accessed over the internet.",
            font=ctk.CTkFont(size=10),
            text_color="#e5a00d",
            justify="left"
        )
        file_warning.grid(row=6, column=0, sticky="w", padx=40, pady=(0, 15))

        # === SAVE BUTTON ===
        def save_and_close():
            self.subtitle_save_method = save_method_var.get()
            self.save_settings()
            self.update_status(f"Settings saved - Using {self.subtitle_save_method} save method")
            settings_window.destroy()

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel",
                                   command=settings_window.destroy,
                                   width=100, fg_color="transparent", border_width=2)
        cancel_btn.pack(side="right", padx=(10, 0))

        save_btn = ctk.CTkButton(button_frame, text="Save Settings",
                                command=save_and_close,
                                width=120)
        save_btn.pack(side="right")


class PlexSubSetterApp(ctk.CTk):
    """Main application class."""

    def __init__(self):
        super().__init__()

        self.title("PlexSubSetter")

        # Start with small default window (will be resized when showing frames)
        self.geometry("500x600")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.current_frame = None
        self.account = None
        self.plex = None
        self.is_closing = False

        # Handle window close event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Show login frame
        self.show_login()

    def on_closing(self):
        """Handle application closing."""
        self.is_closing = True

        # Clean up current frame properly
        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Destroy the window
        try:
            self.quit()
            self.destroy()
        except:
            pass

    def resize_and_center(self, width, height):
        """Resize window and center it on screen."""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def show_login(self):
        """Show login frame."""
        if self.is_closing:
            return

        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Resize for login (small window)
        self.minsize(400, 500)
        self.resize_and_center(500, 600)

        self.current_frame = LoginFrame(self, self.on_login_success)
        self.current_frame.grid(row=0, column=0, sticky="nsew")

    def on_login_success(self, account):
        """Handle successful login."""
        if self.is_closing:
            return
        self.account = account
        self.show_server_selection()

    def show_server_selection(self):
        """Show server selection frame."""
        if self.is_closing:
            return

        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Resize for server selection (medium window)
        self.minsize(600, 500)
        self.resize_and_center(700, 600)

        self.current_frame = ServerSelectionFrame(self, self.account,
                                                  self.on_server_selected,
                                                  self.show_server_selection)
        self.current_frame.grid(row=0, column=0, sticky="nsew")

    def on_server_selected(self, plex):
        """Handle server selection."""
        if self.is_closing:
            return
        self.plex = plex
        self.show_main_app()

    def show_main_app(self):
        """Show main application."""
        if self.is_closing:
            return

        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

        # Resize for main app (large window)
        self.minsize(1000, 750)
        self.resize_and_center(1200, 850)

        self.current_frame = MainAppFrame(self, self.plex, self.show_server_selection)
        self.current_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)


def main():
    """Main entry point."""
    app = PlexSubSetterApp()
    app.mainloop()


if __name__ == '__main__':
    main()
