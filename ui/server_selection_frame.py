"""
Server selection frame for choosing Plex Media Server.
"""

import customtkinter as ctk
import threading
import logging
from error_handling import (
    retry_with_backoff,
    PlexConnectionError,
    PlexAuthenticationError,
    ErrorContext,
    ErrorMessageFormatter,
    get_crash_reporter
)


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
                                   width=100, fg_color="transparent", border_width=2,
                                   text_color=("gray10", "gray90"))
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
        """Connect to selected server with retry logic."""
        self.status_label.configure(text=f"Connecting to {resource.name}...", text_color="yellow")

        def on_retry_callback(func, attempt, error):
            """Update UI during retry attempts."""
            self.after(0, lambda: self.status_label.configure(
                text=f"Connecting to {resource.name}... (attempt {attempt}/3)",
                text_color="yellow"))

        @retry_with_backoff(
            max_attempts=3,
            initial_delay=1.0,
            exceptions=(Exception,),
            on_retry=on_retry_callback
        )
        def connect_with_retry():
            """Connect to Plex server with automatic retry."""
            try:
                plex = resource.connect()
                return plex
            except ConnectionError as e:
                raise PlexConnectionError(resource.name, e)
            except Exception as e:
                # Check if it's an authentication error
                if "unauthorized" in str(e).lower() or "401" in str(e):
                    raise PlexAuthenticationError(e)
                raise PlexConnectionError(resource.name, e)

        def connect_thread():
            try:
                with ErrorContext("server connection", get_crash_reporter()):
                    plex = connect_with_retry()
                    logging.info(f"Successfully connected to Plex server: {resource.name} ({resource.platform})")
                    self.after(0, lambda: self.on_server_selected(plex))
            except (PlexConnectionError, PlexAuthenticationError) as e:
                error_msg = ErrorMessageFormatter.format_plex_error(e.original_error or e, f"server {resource.name}")
                logging.error(error_msg)
                self.after(0, lambda msg=error_msg: self.status_label.configure(
                    text=msg, text_color="red"))
            except Exception as e:
                error_msg = f"Unexpected error connecting to {resource.name}: {e}"
                logging.error(error_msg)
                get_crash_reporter().report_crash(e, {"server": resource.name, "action": "connect"})
                self.after(0, lambda: self.status_label.configure(
                    text=error_msg, text_color="red"))

        threading.Thread(target=connect_thread, daemon=True).start()
