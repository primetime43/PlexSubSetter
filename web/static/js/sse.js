/**
 * SSE (Server-Sent Events) client for PlexSubSetter.
 * Connects to /events and dispatches events to the Alpine.js app state.
 */

(function() {
    let eventSource = null;
    let reconnectDelay = 1000;

    function connect() {
        eventSource = new EventSource('/events');

        eventSource.onopen = function() {
            reconnectDelay = 1000; // Reset on successful connect
        };

        eventSource.addEventListener('progress', function(e) {
            const data = JSON.parse(e.data);
            const appEl = document.querySelector('[x-data]');
            if (appEl && appEl._x_dataStack) {
                Alpine.$data(appEl).handleProgress(data);
            }
        });

        eventSource.addEventListener('task_complete', function(e) {
            const data = JSON.parse(e.data);
            const appEl = document.querySelector('[x-data]');
            if (appEl && appEl._x_dataStack) {
                Alpine.$data(appEl).handleTaskComplete(data);
            }
        });

        eventSource.addEventListener('status', function(e) {
            const data = JSON.parse(e.data);
            // Could update a status bar if needed
        });

        eventSource.addEventListener('log', function(e) {
            const data = JSON.parse(e.data);
            // Could display in a live log panel
        });

        eventSource.addEventListener('subtitle_status', function(e) {
            const data = JSON.parse(e.data);
            const appEl = document.querySelector('[x-data]');
            if (appEl && appEl._x_dataStack) {
                Alpine.$data(appEl).handleSubtitleStatus(data);
            }
        });

        eventSource.addEventListener('subtitle_cache_complete', function(e) {
            const appEl = document.querySelector('[x-data]');
            if (appEl && appEl._x_dataStack) {
                const state = Alpine.$data(appEl);
                state._cacheWaitingFilter = null;
                // Always re-fetch so indicators render from the now-populated cache
                state._fetchItems();
            }
        });

        eventSource.onerror = function() {
            eventSource.close();
            // Reconnect with backoff
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        };
    }

    // Only connect if we're on the app page (not login/servers)
    if (document.querySelector('[x-data]')) {
        connect();
    }
})();
