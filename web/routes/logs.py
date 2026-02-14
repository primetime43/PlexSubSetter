"""Log viewer routes."""

import os
import logging
from flask import Blueprint, render_template, current_app

logs_bp = Blueprint('logs', __name__)

# Max bytes to read from the end of the log file (100KB)
_MAX_LOG_TAIL = 100 * 1024


@logs_bp.route('/logs')
def get_logs():
    """Get log content as HTML partial (last 100KB of log)."""
    log_file = current_app.state.current_log_file
    content = ""
    if log_file and os.path.exists(log_file):
        try:
            file_size = os.path.getsize(log_file)
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                if file_size > _MAX_LOG_TAIL:
                    f.seek(file_size - _MAX_LOG_TAIL)
                    f.readline()  # skip partial first line
                content = f.read()
        except Exception as e:
            content = f"Error reading log file: {e}"

    return render_template('partials/log_modal.html',
                           log_content=content,
                           log_file=log_file or "No log file")
