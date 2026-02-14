"""
Flask application factory for PlexSubSetter web GUI.
"""

import os
import sys
import tempfile
import logging
from flask import Flask
from subliminal import region

from core.session_state import SessionState
from core.task_manager import TaskManager


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )
    app.secret_key = os.urandom(24)

    # App-level globals (single-user local app)
    app.state = SessionState()
    app.task_manager = TaskManager()

    # Configure subliminal cache
    try:
        if sys.platform.startswith('win'):
            os.environ['PYTHONIOENCODING'] = 'utf-8'

        cache_dir = os.path.join(tempfile.gettempdir(), 'plexsubsetter_cache')
        os.makedirs(cache_dir, exist_ok=True)

        if sys.platform.startswith('win'):
            region.configure('dogpile.cache.memory', replace_existing_backend=True)
        else:
            cache_file = os.path.join(cache_dir, 'cachefile.dbm')
            region.configure('dogpile.cache.dbm', arguments={'filename': cache_file}, replace_existing_backend=True)
    except (RuntimeError, ValueError, Exception) as e:
        logging.debug(f"Subliminal cache configuration skipped: {e}")

    # Register blueprints
    from web.routes.auth import auth_bp
    from web.routes.servers import servers_bp
    from web.routes.libraries import libraries_bp
    from web.routes.subtitles import subtitles_bp
    from web.routes.settings import settings_bp
    from web.routes.events import events_bp
    from web.routes.logs import logs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(libraries_bp)
    app.register_blueprint(subtitles_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(logs_bp)

    # Root route - redirect to login or app
    @app.route('/')
    def index():
        from flask import redirect, url_for
        if app.state.plex:
            return redirect(url_for('libraries.app_page'))
        elif app.state.account:
            return redirect(url_for('servers.servers_page'))
        else:
            return redirect(url_for('auth.login_page'))

    return app
