"""
Login frame for Plex OAuth authentication.
"""

import customtkinter as ctk
import threading
import webbrowser
import logging
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from utils.constants import (
    __version__, __author__, __repo__, OAUTH_LOGIN_TIMEOUT,
    COLOR_PLEX_GOLD, COLOR_PLEX_GOLD_HOVER, COLOR_LINK_BLUE,
    COLOR_GRAY, COLOR_STATUS_YELLOW
)


class LoginFrame(ctk.CTkFrame):
    """Login frame for Plex OAuth authentication."""

    def __init__(self, master, on_login_success):
        """
        Initialize the login frame.

        Args:
            master: Parent widget
            on_login_success: Callback function to execute on successful login with account parameter
        """
        super().__init__(master)
        self.on_login_success = on_login_success
        self.pin_login = None

        # Configure grid
        self.grid_columnconfigure(0, weight=1)

        # Title
        title = ctk.CTkLabel(self, text="PlexSubSetter", font=ctk.CTkFont(size=32, weight="bold"))
        title.grid(row=0, column=0, pady=(60, 10), padx=20)

        subtitle = ctk.CTkLabel(self, text="Mass Subtitle Manager for Plex",
                               font=ctk.CTkFont(size=14), text_color=COLOR_GRAY)
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
            fg_color=COLOR_PLEX_GOLD,
            hover_color=COLOR_PLEX_GOLD_HOVER
        )
        self.login_btn.grid(row=1, column=0, pady=(0, 15), sticky="ew", padx=60)

        # Status label
        self.status_label = ctk.CTkLabel(login_frame, text="", wraplength=400)
        self.status_label.grid(row=2, column=0, pady=(15, 0))

        # Info label
        info_text = "You'll be redirected to Plex.tv to sign in securely.\nNo credentials are stored in this application."
        info_label = ctk.CTkLabel(self, text=info_text, font=ctk.CTkFont(size=11),
                                 text_color=COLOR_GRAY, wraplength=400)
        info_label.grid(row=3, column=0, pady=(40, 20))

        # Footer with version, author, and repo link
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=4, column=0, pady=(10, 40))

        version_label = ctk.CTkLabel(footer_frame, text=f"Version {__version__}",
                                     font=ctk.CTkFont(size=10), text_color=COLOR_GRAY)
        version_label.pack(pady=(0, 5))

        author_label = ctk.CTkLabel(footer_frame, text=f"Created by {__author__}",
                                    font=ctk.CTkFont(size=10), text_color=COLOR_GRAY)
        author_label.pack(pady=(0, 5))

        # Clickable repository link
        repo_label = ctk.CTkLabel(footer_frame, text="View on GitHub",
                                  font=ctk.CTkFont(size=10, underline=True),
                                  text_color=COLOR_LINK_BLUE, cursor="hand2")
        repo_label.pack(pady=(0, 10))
        repo_label.bind("<Button-1>", lambda e: webbrowser.open(__repo__))

        # Show Logs button
        logs_btn = ctk.CTkButton(footer_frame, text="📋 Open Logs Folder",
                                command=self.open_logs_folder, height=28,
                                width=150, fg_color="transparent", border_width=1,
                                text_color=("gray10", "gray90"))
        logs_btn.pack()

    def open_logs_folder(self):
        """Open the logs folder in file explorer."""
        import os
        import subprocess
        import platform

        logs_dir = "logs"
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)

        try:
            if platform.system() == "Windows":
                os.startfile(logs_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", logs_dir])
            else:  # Linux
                subprocess.Popen(["xdg-open", logs_dir])
        except Exception as e:
            logging.error(f"Failed to open logs folder: {e}")

    def start_oauth_login(self):
        """Start the OAuth login process."""
        self.login_btn.configure(state="disabled", text="Opening browser...")
        self.status_label.configure(text="Opening your browser for authentication...", text_color=COLOR_STATUS_YELLOW)

        def oauth_thread():
            """Background thread to handle OAuth authentication process."""
            try:
                logging.info("Starting OAuth login process...")

                # Create PIN login with OAuth
                self.pin_login = MyPlexPinLogin(oauth=True)
                logging.info("PIN login created successfully")

                # Get OAuth URL
                oauth_url = self.pin_login.oauthUrl()
                logging.info(f"OAuth URL generated: {oauth_url}")

                # Update UI
                self.after(0, lambda: self.status_label.configure(
                    text="✓ Browser opened! Please sign in to Plex...\n\nWaiting for authentication...",
                    text_color=COLOR_PLEX_GOLD
                ))
                self.after(0, lambda: self.login_btn.configure(text="Waiting for sign in..."))

                # Open browser
                logging.info("Opening browser for OAuth...")
                webbrowser.open(oauth_url)

                # Wait for login with callback
                def on_login(token):
                    """
                    Callback function executed when OAuth login completes.

                    Args:
                        token: OAuth token received from Plex, or None if login failed
                    """
                    if token:
                        logging.info("OAuth token received successfully")
                        try:
                            logging.info("Attempting to create account from token...")
                            account = MyPlexAccount(token=token)
                            logging.info(f"Successfully authenticated as: {account.username}")
                            self.after(0, lambda: self.on_login_success(account))
                        except Exception as e:
                            logging.error(f"Failed to get account from token: {e}", exc_info=True)
                            self.after(0, lambda: self.handle_error(f"Failed to get account: {e}"))
                    else:
                        logging.warning("OAuth login failed or timed out (no token received)")
                        self.after(0, lambda: self.handle_error("Login failed or timed out"))

                # Run with timeout of 5 minutes
                logging.info(f"Waiting for OAuth callback (timeout: {OAUTH_LOGIN_TIMEOUT}s)...")
                self.pin_login.run(callback=on_login, timeout=OAUTH_LOGIN_TIMEOUT)

            except Exception as e:
                logging.error(f"OAuth login error: {e}", exc_info=True)
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
