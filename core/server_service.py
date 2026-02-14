"""
Server discovery and connection service.

Extracted from ui/server_selection_frame.py. No UI dependencies.
"""

import socket
import ipaddress
import logging
from error_handling import (
    retry_with_backoff,
    PlexConnectionError,
    PlexAuthenticationError,
    ErrorContext,
    get_crash_reporter,
)
from utils.constants import CRITICAL_RETRY_ATTEMPTS, CRITICAL_RETRY_DELAY


def get_local_ip_addresses():
    """Get all local IP addresses of this machine."""
    local_ips = []
    try:
        hostname = socket.gethostname()
        local_ips.extend(socket.gethostbyname_ex(hostname)[2])

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ips.append(s.getsockname()[0])
    except Exception as e:
        logging.debug(f"Error getting local IP addresses: {e}")

    return list(set(local_ips))


def is_same_network(local_ips, server_uri):
    """Check if server connection is on the same network."""
    try:
        server_ip = server_uri.split('://')[1].split(':')[0]

        if 'plex.direct' in server_ip:
            return False

        server_addr = ipaddress.ip_address(server_ip)

        for local_ip in local_ips:
            try:
                local_addr = ipaddress.ip_address(local_ip)
                if isinstance(local_addr, ipaddress.IPv4Address) and isinstance(server_addr, ipaddress.IPv4Address):
                    local_network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
                    if server_addr in local_network:
                        return True
            except ValueError:
                continue
    except Exception as e:
        logging.debug(f"Error checking network match: {e}")

    return False


def rank_connection(conn, local_ips):
    """
    Rank connection quality (lower is better).
    Priority: Same-network HTTPS > Same-network HTTP > Remote HTTPS > Remote HTTP
    """
    score = 0
    is_truly_local = is_same_network(local_ips, conn.uri)

    if conn.local and not is_truly_local:
        score += 150
    elif not conn.local and not is_truly_local:
        score += 100

    if not conn.uri.startswith('https'):
        score += 10

    return score


def list_servers(account):
    """
    List all Plex servers from the account with ranked connections.

    Returns:
        list of dicts with server info and ranked connections
    """
    resources = account.resources()
    servers = [r for r in resources if r.product == 'Plex Media Server']

    local_ips = get_local_ip_addresses()
    logging.debug(f"Local IP addresses: {local_ips}")

    result = []
    # Online first, then offline
    online = [s for s in servers if s.presence]
    offline = [s for s in servers if not s.presence]

    for resource in online + offline:
        sorted_connections = sorted(resource.connections, key=lambda c: rank_connection(c, local_ips))
        best = sorted_connections[0] if sorted_connections else None

        connections = []
        for conn in sorted_connections:
            is_best = conn == best
            truly_local = is_same_network(local_ips, conn.uri)

            # Determine type
            if truly_local:
                conn_type = "local"
                conn_desc = "Same Network"
            elif conn.local:
                conn_type = "local"
                conn_desc = "Not Accessible"
            else:
                conn_type = "remote"
                conn_desc = ""

            is_https = conn.uri.startswith('https')

            # Extract display address
            display_addr = conn.uri
            try:
                uri_parts = conn.uri.split('://')
                if len(uri_parts) > 1:
                    host_port = uri_parts[1]
                    if 'plex.direct' in host_port:
                        ip_part = host_port.split('.')[0].replace('-', '.')
                        port = host_port.split(':')[-1] if ':' in host_port else '32400'
                        display_addr = f"{ip_part}:{port}"
                    else:
                        display_addr = host_port
            except Exception:
                pass

            connections.append({
                'uri': conn.uri,
                'local': conn.local,
                'truly_local': truly_local,
                'is_https': is_https,
                'is_best': is_best,
                'conn_type': conn_type,
                'conn_desc': conn_desc,
                'display_addr': display_addr,
            })

        result.append({
            'name': resource.name,
            'presence': resource.presence,
            'platform': resource.platform,
            'platform_version': resource.platformVersion,
            'connections': connections,
            '_resource': resource,  # keep for connect()
        })

    return result


def connect(resource, connection_uri):
    """
    Connect to a Plex server via a specific connection URI.

    Args:
        resource: Plex resource object (from list_servers _resource)
        connection_uri: The URI to connect through

    Returns:
        PlexServer instance
    """
    # Find the matching connection object
    target_conn = None
    for conn in resource.connections:
        if conn.uri == connection_uri:
            target_conn = conn
            break

    if not target_conn:
        raise PlexConnectionError(resource.name, Exception(f"Connection URI not found: {connection_uri}"))

    @retry_with_backoff(
        max_attempts=CRITICAL_RETRY_ATTEMPTS,
        initial_delay=CRITICAL_RETRY_DELAY,
        exceptions=(Exception,),
    )
    def connect_with_retry():
        try:
            original_connections = resource.connections
            resource.connections = [target_conn]
            try:
                plex = resource.connect(timeout=10)
                return plex
            finally:
                resource.connections = original_connections
        except ConnectionError as e:
            raise PlexConnectionError(resource.name, e)
        except Exception as e:
            if "unauthorized" in str(e).lower() or "401" in str(e):
                raise PlexAuthenticationError(e)
            raise PlexConnectionError(resource.name, e)

    with ErrorContext("server connection", get_crash_reporter()):
        plex = connect_with_retry()
        logging.info(f"Successfully connected to Plex server: {resource.name} ({resource.platform}) via {connection_uri}")
        return plex
