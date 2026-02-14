"""Server selection routes."""

import logging
from flask import Blueprint, render_template, jsonify, redirect, url_for, request, current_app

from core import server_service

servers_bp = Blueprint('servers', __name__)

# Cache server list so connect can look up the resource
_server_cache = []


@servers_bp.route('/servers')
def servers_page():
    """Render server selection page."""
    state = current_app.state
    if not state.account:
        return redirect(url_for('auth.login_page'))
    if state.plex:
        return redirect(url_for('libraries.app_page'))

    return render_template('servers.html', username=state.account.username)


@servers_bp.route('/servers/list')
def list_servers():
    """Get server list as JSON (called by htmx on page load)."""
    global _server_cache
    state = current_app.state
    if not state.account:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        servers = server_service.list_servers(state.account)
        _server_cache = servers

        # Strip non-serializable _resource from JSON response
        serializable = []
        for s in servers:
            serializable.append({
                'name': s['name'],
                'presence': s['presence'],
                'platform': s['platform'],
                'platform_version': s['platform_version'],
                'connections': s['connections'],
            })

        return render_template('partials/server_list.html', servers=serializable)
    except Exception as e:
        logging.error(f"Error listing servers: {e}")
        return f'<div class="text-red-400 p-4">Error loading servers: {e}</div>', 500


@servers_bp.route('/servers/connect', methods=['POST'])
def connect_server():
    """Connect to a specific server via a connection URI."""
    global _server_cache
    state = current_app.state
    if not state.account:
        return '', 401

    server_name = request.form.get('server_name')
    connection_uri = request.form.get('connection_uri')

    if not server_name or not connection_uri:
        return '<div class="text-red-400">Missing server name or connection URI</div>', 400

    # Find the resource from cache
    resource = None
    for s in _server_cache:
        if s['name'] == server_name:
            resource = s.get('_resource')
            break

    if not resource:
        return '<div class="text-red-400">Server not found. Please refresh.</div>', 404

    try:
        plex = server_service.connect(resource, connection_uri)
        state.set_plex(plex)
        logging.info(f"Connected to server: {server_name}")
        # Return redirect header for htmx
        return '', 200, {'HX-Redirect': url_for('libraries.app_page')}
    except Exception as e:
        logging.error(f"Error connecting to {server_name}: {e}")
        return f'<div class="text-red-400 p-4">Connection failed: {e}</div>', 500
