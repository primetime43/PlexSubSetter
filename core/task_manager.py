"""
Background task manager with SSE event delivery.

Spawns background threads for long operations and pushes
Server-Sent Events for real-time frontend updates.
"""

import threading
import queue
import uuid
import json
import time
import logging


class TaskManager:
    """Manages background tasks and SSE event delivery."""

    def __init__(self):
        self._tasks = {}  # {task_id: {type, status, result, error}}
        self._lock = threading.Lock()
        self._event_queue = queue.Queue(maxsize=1000)

    def submit(self, task_type, callable_fn, **kwargs):
        """
        Submit a background task.

        Args:
            task_type: String identifying the task type
            callable_fn: Function to run in background thread
            **kwargs: Passed to callable_fn

        Returns:
            task_id: Unique task identifier
        """
        task_id = str(uuid.uuid4())[:8]

        with self._lock:
            self._tasks[task_id] = {
                'type': task_type,
                'status': 'running',
                'result': None,
                'error': None,
            }

        def wrapper():
            try:
                result = callable_fn(**kwargs)
                with self._lock:
                    self._tasks[task_id]['status'] = 'complete'
                    self._tasks[task_id]['result'] = result
                self.emit('task_complete', {
                    'task_id': task_id,
                    'task_type': task_type,
                    'success': True,
                })
            except Exception as e:
                logging.error(f"Task {task_id} ({task_type}) failed: {e}")
                with self._lock:
                    self._tasks[task_id]['status'] = 'error'
                    self._tasks[task_id]['error'] = str(e)
                self.emit('task_complete', {
                    'task_id': task_id,
                    'task_type': task_type,
                    'success': False,
                    'error': str(e),
                })

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        return task_id

    def get_task(self, task_id):
        """Get task status and result."""
        with self._lock:
            return self._tasks.get(task_id)

    def emit(self, event_type, data):
        """
        Push an SSE event to the queue.

        Args:
            event_type: One of 'progress', 'status', 'log', 'task_complete', 'subtitle_status'
            data: Dict of event data
        """
        event = {
            'event': event_type,
            'data': data,
            'id': str(uuid.uuid4())[:8],
            'time': time.time(),
        }
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            # Drop oldest event to make room
            try:
                self._event_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._event_queue.put_nowait(event)
            except queue.Full:
                pass

    def get_events(self):
        """
        Generator that yields SSE-formatted events.
        Blocks waiting for events with periodic keepalive.
        """
        while True:
            try:
                event = self._event_queue.get(timeout=15)
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\nid: {event['id']}\n\n"
            except queue.Empty:
                # Send keepalive comment
                yield ": keepalive\n\n"
