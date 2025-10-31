#!/usr/bin/env python3
"""
PlexSubSetter GUI - Mass Subtitle Finder and Setter for Plex
A modern graphical tool to search, download, and set subtitles for your Plex media library.
"""

import customtkinter as ctk
from tkinter import messagebox
import threading
import configparser
import os
import webbrowser
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from plexapi.server import PlexServer
from plexapi.video import Movie, Episode, Show, Season


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

SET_LANGUAGES = {
    "English": "eng",
    "Spanish": "spa",
    "French": "fre",
    "German": "ger",
    "Italian": "ita",
    "Portuguese": "por",
    "Japanese": "jpn",
    "Korean": "kor",
    "Chinese": "chi",
    "Russian": "rus",
    "Arabic": "ara",
    "Dutch": "dut",
    "Polish": "pol",
    "Swedish": "swe",
    "Danish": "dan",
    "Finnish": "fin",
    "Norwegian": "nor"
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
        info_label.grid(row=3, column=0, pady=(40, 60))

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

                for i, resource in enumerate(servers):
                    def create_server_button(res):
                        # Server card
                        card = ctk.CTkFrame(container)
                        card.grid(row=i, column=0, pady=5, padx=5, sticky="ew")
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

                    self.after(0, lambda r=resource: create_server_button(r))

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
                self.after(ms, func)
            except:
                pass

    def create_widgets(self):
        """Create main application widgets."""

        # === LEFT PANEL: BROWSER ===
        browser_panel = ctk.CTkFrame(self)
        browser_panel.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        browser_panel.grid_columnconfigure(0, weight=1)
        browser_panel.grid_rowconfigure(3, weight=1)  # Updated for search bar

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

        # Search/Filter bar
        search_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        search_frame.grid(row=2, column=0, padx=15, pady=(5, 0), sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="🔍 Search/filter items...",
                                         textvariable=self.search_text, height=32)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        clear_search_btn = ctk.CTkButton(search_frame, text="✕", width=32, height=32,
                                        command=self.clear_search,
                                        fg_color="transparent", hover_color="#404040")
        clear_search_btn.grid(row=0, column=1)

        # Filter status label (shows filter results count)
        self.filter_status_label = ctk.CTkLabel(browser_panel, text="",
                                               font=ctk.CTkFont(size=10), text_color="gray")
        self.filter_status_label.grid(row=2, column=0, padx=15, pady=(35, 0), sticky="w")

        # Browser scrollable frame
        self.browser_scroll = ctk.CTkScrollableFrame(browser_panel, label_text="Select Items")
        self.browser_scroll.grid(row=3, column=0, padx=15, pady=(10, 10), sticky="nsew")
        self.browser_scroll.grid_columnconfigure(0, weight=1)

        # Selection info and controls
        select_control_frame = ctk.CTkFrame(browser_panel, fg_color="transparent")
        select_control_frame.grid(row=4, column=0, padx=15, pady=(0, 15), sticky="ew")
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
        right_panel.grid_rowconfigure(4, weight=1)

        # === HEADER ===
        header_frame = ctk.CTkFrame(right_panel)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(header_frame, text=f"📺 {self.plex.friendlyName}",
                            font=ctk.CTkFont(size=24, weight="bold"))
        title.grid(row=0, column=0, sticky="w", padx=15, pady=15)

        logout_btn = ctk.CTkButton(header_frame, text="Change Server", command=self.on_logout,
                                   width=120, fg_color="transparent", border_width=2)
        logout_btn.grid(row=0, column=1, padx=15, pady=15)

        # === SUBTITLE OPTIONS ===
        options_frame = ctk.CTkFrame(right_panel)
        options_frame.grid(row=1, column=0, sticky="ew", pady=10)
        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=1)

        # Left column - Search language
        left_col = ctk.CTkFrame(options_frame, fg_color="transparent")
        left_col.grid(row=0, column=0, padx=(15, 10), pady=15, sticky="ew")

        ctk.CTkLabel(left_col, text="Search Language:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.search_lang_combo = ctk.CTkComboBox(left_col, values=list(SEARCH_LANGUAGES.keys()),
                                                 state="readonly")
        self.search_lang_combo.set("English")
        self.search_lang_combo.pack(fill="x", pady=(5, 10))

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

        # Right column - Set language
        right_col = ctk.CTkFrame(options_frame, fg_color="transparent")
        right_col.grid(row=0, column=1, padx=(10, 15), pady=15, sticky="ew")

        ctk.CTkLabel(right_col, text="Set Language:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.set_lang_combo = ctk.CTkComboBox(right_col, values=list(SET_LANGUAGES.keys()),
                                             state="readonly")
        self.set_lang_combo.set("English")
        self.set_lang_combo.pack(fill="x", pady=(5, 0))

        # === ACTION BUTTONS ===
        actions_frame = ctk.CTkFrame(right_panel)
        actions_frame.grid(row=2, column=0, sticky="ew", pady=10)

        for i in range(4):
            actions_frame.grid_columnconfigure(i, weight=1)

        self.search_btn = ctk.CTkButton(actions_frame, text="🔍 Search & Download",
                                       command=self.search_subtitles, height=40,
                                       state="disabled")
        self.search_btn.grid(row=0, column=0, padx=5, pady=15, sticky="ew")

        self.list_btn = ctk.CTkButton(actions_frame, text="📋 List Subtitles",
                                     command=self.list_subtitles, height=40,
                                     fg_color="#1f538d", hover_color="#1a4472",
                                     state="disabled")
        self.list_btn.grid(row=0, column=1, padx=5, pady=15, sticky="ew")

        self.set_btn = ctk.CTkButton(actions_frame, text="✓ Set Language",
                                    command=self.set_subtitles, height=40,
                                    fg_color="#2d7a2d", hover_color="#236123",
                                    state="disabled")
        self.set_btn.grid(row=0, column=2, padx=5, pady=15, sticky="ew")

        self.disable_btn = ctk.CTkButton(actions_frame, text="✗ Disable Subtitles",
                                        command=self.disable_subtitles, height=40,
                                        fg_color="#8b0000", hover_color="#6b0000",
                                        state="disabled")
        self.disable_btn.grid(row=0, column=3, padx=5, pady=15, sticky="ew")

        # === OUTPUT LOG ===
        log_frame = ctk.CTkFrame(right_panel)
        log_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(log_header, text="Output Log", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w")

        clear_btn = ctk.CTkButton(log_header, text="Clear", command=self.clear_log,
                                 width=80, height=24)
        clear_btn.grid(row=0, column=1, sticky="e")

        # Text widget with proper wrapping
        self.output_text = ctk.CTkTextbox(log_frame, wrap="word", height=250, font=ctk.CTkFont(size=12))
        self.output_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")

        # === PROGRESS BAR ===
        self.progress_bar = ctk.CTkProgressBar(right_panel, mode="indeterminate")
        self.progress_bar.grid(row=5, column=0, sticky="ew", pady=(10, 0))
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

    def filter_items(self):
        """Filter displayed items based on search text (top-level only: show/movie names)."""
        search_query = self.search_text.get().lower().strip()

        if not search_query:
            # No filter - show all items
            for frame in self.top_level_frames:
                try:
                    frame.pack(fill="x", pady=2, padx=5)
                except:
                    pass
            self.filter_status_label.configure(text="")
            return

        # Filter items - only check top-level names (shows/movies)
        visible_count = 0
        total_count = len(self.top_level_frames)

        for frame in self.top_level_frames:
            match_found = False

            # Check if it's a show frame (has show_obj attribute)
            if hasattr(frame, 'show_obj'):
                # For shows, only check the show title (no deep search)
                show = frame.show_obj
                if search_query in show.title.lower():
                    match_found = True
            else:
                # For movies, check the checkbox text
                for child in frame.winfo_children():
                    if isinstance(child, ctk.CTkCheckBox):
                        checkbox_text = child.cget("text").lower()
                        if search_query in checkbox_text:
                            match_found = True
                            break

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
        if visible_count == total_count:
            self.filter_status_label.configure(text="")
        else:
            self.filter_status_label.configure(
                text=f"Showing {visible_count} of {total_count} items",
                text_color="#e5a00d"
            )

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
        """Populate browser with movies."""
        # Clear any loading indicator
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()

        # Clear top-level frames list
        self.top_level_frames.clear()

        for movie in movies:
            var = ctk.BooleanVar()
            frame = ctk.CTkFrame(self.browser_scroll, fg_color="transparent")
            frame.pack(fill="x", pady=2, padx=5)

            cb = ctk.CTkCheckBox(frame, text=f"{movie.title} ({movie.year})",
                                variable=var,
                                command=lambda m=movie, v=var: self.on_item_selected(m, v))
            cb.pack(side="left", fill="x", expand=True)

            # Store frame for filtering
            self.top_level_frames.append(frame)

    def populate_shows(self, shows):
        """Populate browser with shows (expandable)."""
        # Clear any loading indicator
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()

        # Clear top-level frames list
        self.top_level_frames.clear()

        for show in shows:
            # Show frame
            show_frame = ctk.CTkFrame(self.browser_scroll, fg_color="transparent")
            show_frame.pack(fill="x", pady=2, padx=5)

            # Show checkbox and expand button
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
                                     command=lambda s=show, v=show_var: self.on_show_selected(s, v))
            show_cb.pack(side="left", fill="x", expand=True)

            # Store references
            show_frame.expand_btn = expand_btn
            show_frame.expand_var = expand_var
            show_frame.show_var = show_var
            show_frame.show_obj = show

            # Store frame for filtering
            self.top_level_frames.append(show_frame)

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
                                       command=lambda s=season, v=season_var: self.on_season_selected(s, v))
            season_cb.pack(side="left")

            season_frame.expand_btn = expand_btn
            season_frame.expand_var = expand_var
            season_frame.season_var = season_var
            season_frame.season_obj = season
            season_frame.season_inner = season_inner

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
        """Populate episodes under a season."""
        episode_container = ctk.CTkFrame(season_frame, fg_color="transparent")
        episode_container.pack(fill="x", padx=(25, 0), pady=(2, 0))

        for episode in episodes:
            episode_var = ctk.BooleanVar()

            # Create a frame for each episode for better layout
            ep_frame = ctk.CTkFrame(episode_container, fg_color="transparent")
            ep_frame.pack(fill="x", pady=1)

            ep_cb = ctk.CTkCheckBox(ep_frame,
                                   text=f"E{episode.index:02d} - {episode.title}",
                                   variable=episode_var,
                                   command=lambda e=episode, v=episode_var: self.on_item_selected(e, v))
            ep_cb.pack(anchor="w", padx=(5, 0))

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

    def on_show_selected(self, show, var):
        """Handle show selection (selects all episodes)."""
        def load_and_select():
            if self._is_destroyed:
                return
            try:
                episodes = show.episodes()
                if var.get():
                    # Show summary for the show
                    self.safe_after(0, lambda: self.log(f"\n📺 {show.title} - Selected all {len(episodes)} episodes"))
                    self.safe_after(0, lambda: self.log(f"  Tip: Expand seasons and click individual episodes to see their subtitle status"))

                    for ep in episodes:
                        if ep not in self.selected_items:
                            self.selected_items.append(ep)
                else:
                    for ep in episodes:
                        if ep in self.selected_items:
                            self.selected_items.remove(ep)
                self.safe_after(0, self.update_selection_label)
            except Exception as e:
                self.safe_after(0, lambda: self.log(f"Error: {e}"))

        threading.Thread(target=load_and_select, daemon=True).start()

    def on_season_selected(self, season, var):
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

                    # Show subtitle status for all episodes in the season
                    for ep in episodes:
                        self.show_subtitle_status(ep)
                else:
                    for ep in episodes:
                        if ep in self.selected_items:
                            self.selected_items.remove(ep)
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

        # Enable/disable action buttons
        state = "normal" if count > 0 else "disabled"
        self.search_btn.configure(state=state)
        self.list_btn.configure(state=state)
        self.set_btn.configure(state=state)
        self.disable_btn.configure(state=state)

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

                                # Check if this subtitle is selected
                                is_selected = False
                                if hasattr(sub, 'selected'):
                                    is_selected = bool(sub.selected)

                                status = "[SEL]" if is_selected else "     "

                                # Store info for all subtitles
                                sub_info = f"{status} {lang} ({codec}) {forced} {sdh}".strip()
                                all_subs_info.append(sub_info)

                                if is_selected and not selected_sub:
                                    selected_sub = f"{lang} ({codec}) {forced} {sdh}".strip()

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

    def get_video_items(self):
        """Get selected video items."""
        return self.selected_items

    def search_subtitles(self):
        """Search and download subtitles."""
        def task():
            self.show_progress()
            self.disable_action_buttons()

            self.log("\n" + "="*60)
            self.log("SEARCHING FOR SUBTITLES")
            self.log("="*60)

            items = self.get_video_items()
            if not items:
                self.log("✗ No items selected\n")
                self.hide_progress()
                self.enable_action_buttons()
                return

            language_name = self.search_lang_combo.get()
            language = SEARCH_LANGUAGES[language_name]
            sdh = self.sdh_var.get()
            forced = self.forced_var.get()

            self.log(f"Processing {len(items)} item(s)...")
            self.log(f"Language: {language_name} ({language}), SDH: {sdh}, Forced: {forced}\n")

            for item in items:
                title = self._get_item_title(item)
                try:
                    subtitles = item.searchSubtitles(language=language,
                                                    hearingImpaired=sdh,
                                                    forced=forced)
                    if subtitles:
                        self.log(f"✓ {title} - {len(subtitles)} subtitle(s) found")
                        item.downloadSubtitles(subtitles[0])
                        self.log(f"    → Downloading...")
                    else:
                        self.log(f"  {title} - No subtitles found")
                except Exception as e:
                    self.log(f"✗ {title} - {e}")

            self.log("\n✓ Search completed\n")
            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

    def list_subtitles(self):
        """List available subtitles."""
        def task():
            self.show_progress()
            self.disable_action_buttons()

            self.log("\n" + "="*60)
            self.log("LISTING SUBTITLE STREAMS")
            self.log("="*60)

            items = self.get_video_items()
            if not items:
                self.log("✗ No items selected\n")
                self.hide_progress()
                self.enable_action_buttons()
                return

            self.log(f"Processing {len(items)} item(s)...\n")

            for item in items:
                title = self._get_item_title(item)
                self.log(f"{title}:")

                try:
                    has_subs = False
                    for media in item.media:
                        for part in media.parts:
                            subs = part.subtitleStreams()
                            if subs:
                                has_subs = True
                                for sub in subs:
                                    selected = "[SEL]" if sub.selected else "     "
                                    language = sub.language or "Unknown"
                                    codec = sub.codec or "?"
                                    forced = "[F]" if sub.forced else ""
                                    sdh = "[SDH]" if sub.hearingImpaired else ""
                                    self.log(f"  {selected} {language:12} ({codec:3}) {forced:4} {sdh}")

                    if not has_subs:
                        self.log("  No subtitle streams")
                except Exception as e:
                    self.log(f"  ✗ Error: {e}")

                self.log("")

            self.log("✓ Listing completed\n")
            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

    def set_subtitles(self):
        """Set subtitle by language."""
        def task():
            self.show_progress()
            self.disable_action_buttons()

            self.log("\n" + "="*60)
            self.log("SETTING SUBTITLE STREAMS")
            self.log("="*60)

            items = self.get_video_items()
            if not items:
                self.log("✗ No items selected\n")
                self.hide_progress()
                self.enable_action_buttons()
                return

            language_name = self.set_lang_combo.get()
            language = SET_LANGUAGES[language_name]
            self.log(f"Processing {len(items)} item(s)...")
            self.log(f"Setting to: {language_name} ({language})\n")

            success_count = 0
            for item in items:
                title = self._get_item_title(item)
                try:
                    found = False
                    for media in item.media:
                        for part in media.parts:
                            subs = part.subtitleStreams()
                            target_sub = next((s for s in subs if s.languageCode == language), None)
                            if target_sub:
                                part.setSelectedSubtitleStream(target_sub)
                                self.log(f"✓ {title}")
                                found = True
                                success_count += 1
                                break
                    if not found:
                        self.log(f"  {title} - No {language_name} subtitles")
                except Exception as e:
                    self.log(f"✗ {title} - {e}")

            self.log(f"\n✓ Set {success_count}/{len(items)} items\n")
            self.hide_progress()
            self.enable_action_buttons()

        threading.Thread(target=task, daemon=True).start()

    def disable_subtitles(self):
        """Disable all subtitles."""
        def task():
            self.show_progress()
            self.disable_action_buttons()

            self.log("\n" + "="*60)
            self.log("DISABLING SUBTITLES")
            self.log("="*60)

            items = self.get_video_items()
            if not items:
                self.log("✗ No items selected\n")
                self.hide_progress()
                self.enable_action_buttons()
                return

            self.log(f"Processing {len(items)} item(s)...\n")

            for item in items:
                title = self._get_item_title(item)
                try:
                    for media in item.media:
                        for part in media.parts:
                            part.resetSelectedSubtitleStream()
                    self.log(f"✓ {title}")
                except Exception as e:
                    self.log(f"✗ {title} - {e}")

            self.log("\n✓ Disabling completed\n")
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
        self.list_btn.configure(state="disabled")
        self.set_btn.configure(state="disabled")
        self.disable_btn.configure(state="disabled")
        self.refresh_browser_btn.configure(state="disabled")

    def enable_action_buttons(self):
        """Enable action buttons if items selected."""
        state = "normal" if self.selected_items else "disabled"
        self.search_btn.configure(state=state)
        self.list_btn.configure(state=state)
        self.set_btn.configure(state=state)
        self.disable_btn.configure(state=state)
        self.refresh_browser_btn.configure(state="normal")

    def _get_item_title(self, item):
        """Get formatted title."""
        if isinstance(item, Movie):
            return f"{item.title} ({item.year})"
        elif isinstance(item, Episode):
            return f"{item.grandparentTitle} S{item.seasonNumber:02d}E{item.index:02d} - {item.title}"
        else:
            return item.title


class PlexSubSetterApp(ctk.CTk):
    """Main application class."""

    def __init__(self):
        super().__init__()

        self.title("PlexSubSetter")

        # Set window size and center it
        window_width = 1200
        window_height = 850
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.geometry(f'{window_width}x{window_height}+{x}+{y}')

        # Set minimum window size
        self.minsize(1000, 750)

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

    def show_login(self):
        """Show login frame."""
        if self.is_closing:
            return

        if self.current_frame:
            try:
                self.current_frame.destroy()
            except:
                pass

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

        self.current_frame = MainAppFrame(self, self.plex, self.show_server_selection)
        self.current_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)


def main():
    """Main entry point."""
    app = PlexSubSetterApp()
    app.mainloop()


if __name__ == '__main__':
    main()
