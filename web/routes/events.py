"""SSE (Server-Sent Events) route."""

from flask import Blueprint, Response, current_app

events_bp = Blueprint('events', __name__)


@events_bp.route('/events')
def event_stream():
    """SSE endpoint - streams events from TaskManager."""
    tm = current_app.task_manager

    def generate():
        for event in tm.get_events():
            yield event

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
