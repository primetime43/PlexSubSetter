"""
Login frame for Plex OAuth authentication.
"""

import customtkinter as ctk
import threading
import webbrowser
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from utils.constants import __version__, __author__, __repo__


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
        repo_label = ctk.CTkLabel(footer_frame, text="View on GitHub",
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
