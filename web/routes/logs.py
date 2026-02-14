"""Log viewer routes."""

import os
import logging
from flask import Blueprint, render_template, current_app

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/logs')
def get_logs():
    """Get log content as HTML partial."""
    log_file = current_app.state.current_log_file
    content = ""
    if log_file and os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            content = f"Error reading log file: {e}"

    return render_template('partials/log_modal.html',
                           log_content=content,
                           log_file=log_file or "No log file")
