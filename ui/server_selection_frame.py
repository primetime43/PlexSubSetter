"""
Server selection frame for choosing Plex Media Server.
"""

import customtkinter as ctk
import threading
import logging
import socket
import ipaddress
from error_handling import (
    retry_with_backoff,
    PlexConnectionError,
    PlexAuthenticationError,
    ErrorContext,
    ErrorMessageFormatter,
    get_crash_reporter
)
from utils.constants import (
    CRITICAL_RETRY_ATTEMPTS, CRITICAL_RETRY_DELAY,
    COLOR_STATUS_GREEN, COLOR_STATUS_RED, COLOR_STATUS_YELLOW, COLOR_GRAY
)


class ServerSelectionFrame(ctk.CTkFrame):
    """Server selection frame."""

    @staticmethod
    def get_local_ip_addresses():
        """
        Get all local IP addresses of this machine.

        Returns:
            list: List of local IP address strings
        """
        local_ips = []
        try:
            # Get hostname and resolve to IPs
            hostname = socket.gethostname()
            local_ips.extend(socket.gethostbyname_ex(hostname)[2])

            # Also try to get IP by connecting to external host (doesn't actually connect)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ips.append(s.getsockname()[0])
        except Exception as e:
            logging.debug(f"Error getting local IP addresses: {e}")

        return list(set(local_ips))  # Remove duplicates

    @staticmethod
    def is_same_network(local_ips, server_uri):
        """
        Check if server connection is on the same network as this machine.

        Args:
            local_ips: List of local IP addresses
            server_uri: Server connection URI (e.g., "http://192.168.1.100:32400")

        Returns:
            bool: True if on same network, False otherwise
        """
        try:
            # Extract IP from URI
            server_ip = server_uri.split('://')[1].split(':')[0]

            # Skip if it's a plex.direct domain
            if 'plex.direct' in server_ip:
                return False

            # Convert to IP addresses for comparison
            server_addr = ipaddress.ip_address(server_ip)

            for local_ip in local_ips:
                try:
                    local_addr = ipaddress.ip_address(local_ip)

                    # Check if same subnet (assuming /24 for common home networks)
                    # Compare first 3 octets for IPv4
                    if isinstance(local_addr, ipaddress.IPv4Address) and isinstance(server_addr, ipaddress.IPv4Address):
                        local_network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
                        if server_addr in local_network:
                            return True
                except ValueError:
                    continue

        except Exception as e:
            logging.debug(f"Error checking network match: {e}")

        return False

    def __init__(self, master, account, on_server_selected, on_logout):
        """
        Initialize the server selection frame.

        Args:
            master: Parent widget
            account: Authenticated MyPlexAccount instance
            on_server_selected: Callback function executed when server is selected with plex parameter
            on_logout: Callback function to execute on logout
        """
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
        subtitle = ctk.CTkLabel(self, text="Select a server connection to manage subtitles",
                               font=ctk.CTkFont(size=14))
        subtitle.grid(row=1, column=0, pady=(0, 10), padx=20)

        # Servers container
        servers_frame = ctk.CTkScrollableFrame(self, label_text="Available Servers")
        servers_frame.grid(row=2, column=0, pady=10, padx=40, sticky="nsew")
        servers_frame.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Status label
        self.status_label = ctk.CTkLabel(self, text="Loading servers...", text_color=COLOR_STATUS_YELLOW)
        self.status_label.grid(row=3, column=0, pady=10)

        # Load servers
        self.load_servers(servers_frame)

    def load_servers(self, container):
        """Load available Plex servers."""
        def load_thread():
            """Background thread to load servers from Plex account."""
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
                        """
                        Create a server card button in the UI.

                        Args:
                            res: Plex server resource object
                            row_index: Grid row position for the server card
                        """
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
                        status_color = COLOR_STATUS_GREEN if res.presence else COLOR_STATUS_RED
                        status_label = ctk.CTkLabel(card, text=status, anchor="w", text_color=status_color)
                        status_label.grid(row=1, column=0, sticky="w", padx=15, pady=(0, 5))

                        # Platform info
                        platform_text = f"Platform: {res.platform} | Version: {res.platformVersion}"
                        platform_label = ctk.CTkLabel(card, text=platform_text, anchor="w",
                                                     text_color=COLOR_GRAY, font=ctk.CTkFont(size=11))
                        platform_label.grid(row=2, column=0, sticky="w", padx=15, pady=(0, 10))

                        # Connections label
                        conn_header = ctk.CTkLabel(card, text="Available Connections:",
                                                  font=ctk.CTkFont(size=12, weight="bold"),
                                                  anchor="w")
                        conn_header.grid(row=3, column=0, sticky="w", padx=15, pady=(5, 5))

                        # Sort and rank connections by quality
                        connections = res.connections

                        # Get local machine's IP addresses
                        local_ips = self.get_local_ip_addresses()
                        logging.debug(f"Local IP addresses: {local_ips}")

                        def rank_connection(conn):
                            """
                            Rank connection quality (lower is better).
                            Priority: Same-network HTTPS > Same-network HTTP > Remote HTTPS > Remote HTTP
                            """
                            score = 0

                            # Check if we're actually on the same network
                            is_truly_local = self.is_same_network(local_ips, conn.uri)

                            # If marked as local but we're not on same network, deprioritize
                            if conn.local and not is_truly_local:
                                score += 150  # Worse than remote connections
                            elif not conn.local and not is_truly_local:
                                score += 100  # Remote connection
                            # else: truly local connection (score += 0, highest priority)

                            # HTTPS is more secure
                            if not conn.uri.startswith('https'):
                                score += 10

                            return score

                        sorted_connections = sorted(connections, key=rank_connection)
                        best_connection = sorted_connections[0] if sorted_connections else None

                        # Show all connections with recommendations
                        for conn_idx, conn in enumerate(sorted_connections):
                            is_best = conn == best_connection
                            is_truly_local = self.is_same_network(local_ips, conn.uri)

                            # Determine connection type display
                            if is_truly_local:
                                conn_type = "🏠 Local"
                                conn_desc = "(Same Network)"
                            elif conn.local:
                                conn_type = "🏠 Local"
                                conn_desc = "(Not Accessible)"
                            else:
                                conn_type = "🌐 Remote"
                                conn_desc = ""

                            protocol = "🔒" if conn.uri.startswith('https') else "🔓"

                            # Extract IP:port from URI for compact display
                            try:
                                # Parse URI to get host:port
                                uri_parts = conn.uri.split('://')
                                if len(uri_parts) > 1:
                                    host_port = uri_parts[1]
                                    # For plex.direct URLs, extract the IP portion
                                    if 'plex.direct' in host_port:
                                        # Example: 192-168-1-100.xxx.plex.direct:32400 -> 192.168.1.100:32400
                                        ip_part = host_port.split('.')[0].replace('-', '.')
                                        port = host_port.split(':')[-1] if ':' in host_port else '32400'
                                        display_addr = f"{ip_part}:{port}"
                                    else:
                                        display_addr = host_port
                                else:
                                    display_addr = conn.uri
                            except Exception:
                                display_addr = conn.uri

                            # Build connection text with recommendation
                            if is_best:
                                conn_text = f"⭐ RECOMMENDED  |  {conn_type} {conn_desc}  |  {protocol} {display_addr}"
                                fg_color = (COLOR_STATUS_GREEN, "#1e5631")
                                hover_color = ("#27ae60", "#1a4d28")
                                font_weight = "bold"
                            else:
                                if conn_desc:
                                    conn_text = f"{conn_type} {conn_desc}  |  {protocol} {display_addr}"
                                else:
                                    conn_text = f"{conn_type}  |  {protocol} {display_addr}"
                                fg_color = ("gray85", "gray25")
                                hover_color = ("gray75", "gray35")
                                font_weight = "normal"

                            # Store full URI for the connection callback
                            def make_connection_handler(connection, full_uri):
                                """Create connection handler with full URI for status display."""
                                def handler():
                                    # Show full URI in status when connecting
                                    self.status_label.configure(
                                        text=f"Connecting via {full_uri}...",
                                        text_color=COLOR_STATUS_YELLOW
                                    )
                                    self.connect_to_server_via_connection(res, connection)
                                return handler

                            conn_btn = ctk.CTkButton(
                                card,
                                text=conn_text,
                                command=make_connection_handler(conn, conn.uri),
                                width=500,
                                height=32,
                                anchor="w",
                                font=ctk.CTkFont(size=11, weight=font_weight),
                                fg_color=fg_color,
                                hover_color=hover_color
                            )
                            conn_btn.grid(row=4+conn_idx, column=0, sticky="ew", padx=15, pady=2)

                        # Add bottom padding
                        bottom_spacer = ctk.CTkLabel(card, text="", height=10)
                        bottom_spacer.grid(row=4+len(sorted_connections), column=0)

                    self.after(0, lambda r=resource, idx=i: create_server_button(r, idx))

            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"Error loading servers: {e}", text_color="red"))

        threading.Thread(target=load_thread, daemon=True).start()

    def connect_to_server_via_connection(self, resource, connection):
        """
        Connect to selected server via a specific connection with retry logic.

        Args:
            resource: Plex server resource object
            connection: Specific connection object to use
        """
        conn_type = "local" if connection.local else "remote"
        self.status_label.configure(
            text=f"Connecting to {resource.name} via {conn_type} ({connection.uri})...",
            text_color=COLOR_STATUS_YELLOW
        )

        def on_retry_callback(func, attempt, error):
            """Update UI during retry attempts."""
            self.after(0, lambda: self.status_label.configure(
                text=f"Connecting to {resource.name} via {connection.uri}... (attempt {attempt}/{CRITICAL_RETRY_ATTEMPTS})",
                text_color=COLOR_STATUS_YELLOW))

        @retry_with_backoff(
            max_attempts=CRITICAL_RETRY_ATTEMPTS,
            initial_delay=CRITICAL_RETRY_DELAY,
            exceptions=(Exception,),
            on_retry=on_retry_callback
        )
        def connect_with_retry():
            """Connect to Plex server with automatic retry."""
            try:
                # Temporarily replace resource.connections with only the selected one
                original_connections = resource.connections
                resource.connections = [connection]

                try:
                    # Use shorter timeout for direct connection
                    plex = resource.connect(timeout=10)
                    return plex
                finally:
                    # Restore original connections
                    resource.connections = original_connections

            except ConnectionError as e:
                raise PlexConnectionError(resource.name, e)
            except Exception as e:
                # Check if it's an authentication error
                if "unauthorized" in str(e).lower() or "401" in str(e):
                    raise PlexAuthenticationError(e)
                raise PlexConnectionError(resource.name, e)

        def connect_thread():
            """Background thread to connect to selected Plex server."""
            try:
                with ErrorContext("server connection", get_crash_reporter()):
                    plex = connect_with_retry()
                    logging.info(f"Successfully connected to Plex server: {resource.name} ({resource.platform}) via {connection.uri}")
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
