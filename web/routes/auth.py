"""Authentication routes."""

import logging
from flask import Blueprint, render_template, jsonify, redirect, url_for, current_app

from core import auth_service
from utils.constants import __version__, __author__, __repo__

auth_bp = Blueprint('auth', __name__)

# Module-level pin_login storage (single-user app)
_pin_login = None


@auth_bp.route('/login')
def login_page():
    """Render login page."""
    if current_app.state.plex:
        return redirect(url_for('libraries.app_page'))
    if current_app.state.account:
        return redirect(url_for('servers.servers_page'))
    return render_template('login.html',
                           version=__version__,
                           author=__author__,
                           repo=__repo__)


@auth_bp.route('/auth/start-oauth', methods=['POST'])
def start_oauth():
    """Start OAuth flow, return the URL to open."""
    global _pin_login
    try:
        _pin_login, oauth_url = auth_service.start_oauth()
        return jsonify({'oauth_url': oauth_url})
    except Exception as e:
        logging.error(f"OAuth start error: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/auth/poll-oauth')
def poll_oauth():
    """Poll for OAuth completion."""
    global _pin_login
    if _pin_login is None:
        return jsonify({'status': 'no_session'}), 400

    try:
        account = auth_service.poll_oauth(_pin_login)
        if account:
            current_app.state.set_account(account)
            _pin_login = None
            return jsonify({'status': 'authenticated', 'username': account.username})
        else:
            return jsonify({'status': 'pending'})
    except Exception as e:
        logging.error(f"OAuth poll error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@auth_bp.route('/auth/logout', methods=['POST'])
def logout():
    """Clear session and redirect to login."""
    current_app.state.clear_auth()
    return redirect(url_for('auth.login_page'))


@auth_bp.route('/auth/status')
def auth_status():
    """Check current auth state."""
    state = current_app.state
    if state.plex:
        return jsonify({'state': 'connected', 'server': state.plex.friendlyName})
    elif state.account:
        return jsonify({'state': 'authenticated', 'username': state.account.username})
    else:
        return jsonify({'state': 'unauthenticated'})
